# Elevance Prior Authorization Evidence Assistant — Full Architecture

> **One-page reference** — A complete description of how a PA request flows from provider submission through the five-agent AI pipeline to a nurse's final decision.

---

## High-Level Architecture

```mermaid
flowchart TD
    subgraph FRONTEND["Frontend — React + TypeScript (Vite, port 5173)"]
        ID["IntakeDashboard\nSubmit PA case + upload documents"]
        NRW["NurseReviewWorkspace\nReview completeness report + claim + decide"]
        OD["OperationsDashboard\nSLA metrics, queue stats, audit log"]
    end

    subgraph API["FastAPI Backend (port 8000)"]
        IR["intake_routes\nPOST /api/v1/intake/cases\nPOST /api/v1/intake/cases/id/documents"]
        RR["review_routes\nGET /api/v1/review/cases\nPOST /api/v1/review/cases/id/claim\nPOST /api/v1/review/cases/id/decision\nPOST /api/v1/review/cases/id/checklist/item/override"]
        OPR["ops_routes\n/api/v1/ops/*"]
        AUR["audit_routes\n/api/v1/audit/*"]
        ADR["admin_routes\n/api/v1/admin/*"]
        HP["/health\n/health/readiness"]
    end

    subgraph AGENTS["Five-Agent Pipeline"]
        A1["Agent 1 — Intake and Classification\nIntakeClassificationAgent\nextract_requirements()"]
        A2["Agent 2 — Evidence Retrieval RAG\nEvidenceRetrievalAgent\nretrieve() and index_case_document()"]
        A3["Agent 3 — Policy Reasoning and Gap Analysis\nPolicyReasoningAgent\nassess_requirements()"]
        A4["Agent 4 — Reviewer Summary and Communication\nReviewerSummaryAgent\ndraft_provider_communication()"]
        A5["Agent 5 — Workflow and Audit\nWorkflowAgent\nroute_case() and check_readiness()"]
    end

    subgraph PIPELINE["Completeness Pipeline Orchestrator"]
        CP["completeness_pipeline\nrun_completeness_pipeline()\nOrchestrates A2 then A3 then persist then advance status"]
    end

    subgraph SERVICES["Processing Services"]
        PDF["pdf_service\nextract_text_from_pdf()"]
        CHK["chunking_service\nchunk_pages()"]
        QDS["qdrant_service\nQdrantIndexingService\nindex_text_chunks()\nsearch_dense() and search_sparse()"]
        FUS["fusion_service\nreciprocal_rank_fusion()\nFusedResult with keyword_miss flag"]
        SLA["sla_service\nrun_sla_check_loop() every 5 min\nescalate_sla_breached_cases()"]
    end

    subgraph INFRA["Local Infrastructure - Docker"]
        PG["PostgreSQL :5433\npa_evidence DB\nCases, Documents, Policies\nPolicyRequirements\nCompletenessReportItems, AuditLog"]
        MINIO["MinIO :9000\nObject Storage\npa-case-documents bucket\nraw PDF/Scan/Fax files"]
        QDRANT["Qdrant :6333\nVector Store\nCollection: pa-evidence\nDense 1024-dim + Sparse BM25"]
        OLLAMA["Ollama :11434\nLocal LLM - llama3.1\nOpenAI-compat /v1/chat/completions"]
        TEI["TEI :8080\nLocal Embedding Server\nBAAI/bge-large-en-v1.5\n1024-dim dense embeddings"]
    end

    ID -->|HTTP REST| IR
    NRW -->|HTTP REST| RR
    OD -->|HTTP REST| OPR
    OD -->|HTTP REST| AUR

    IR -->|"Triggers A1 on policy PDF"| A1
    IR -->|"Spawns background task"| CP
    RR -->|"Reject triggers A4"| A4
    HP -->|"Readiness probe"| A5

    CP --> A2
    CP --> A3
    CP -->|"Persist results"| PG

    A1 -->|"Policy text to LLM"| OLLAMA
    A2 -->|"Query text to embedding"| TEI
    A2 -->|"Dense search"| QDS
    A2 -->|"Sparse search"| QDS
    QDS -->|"Results per leg"| FUS
    FUS -->|"FusedResult + keyword_miss"| A3
    A3 -->|"Evidence + prompt to LLM"| OLLAMA
    A4 -->|"Gap items + prompt to LLM"| OLLAMA

    MINIO -->|"Download PDF bytes"| PDF
    PDF -->|"Page text list"| CHK
    CHK -->|"TextChunk list"| QDS
    QDS -->|"Dense embed via TEI"| TEI
    QDS -->|"Index points"| QDRANT

    A5 -->|"Probes health"| OLLAMA
    A5 -->|"Probes health"| TEI
    A5 -->|"Probes health"| QDRANT
    A5 -->|"Probes health"| MINIO
    SLA -->|"Scan in_nurse_review cases"| PG
    SLA -->|"Escalate and write AuditLog"| PG
    IR -->|"Store case + document metadata"| PG
    IR -->|"Upload raw files"| MINIO
    RR -->|"Read/write case state"| PG
    OPR -->|"Read queue stats"| PG
    AUR -->|"Read audit log"| PG
```

---

## Phase 1 — Case Submission

```mermaid
sequenceDiagram
    participant Provider as Provider / Intake UI
    participant IR as intake_routes
    participant PG as PostgreSQL
    participant MINIO as MinIO
    participant BG as Background Task

    Provider->>IR: POST /api/v1/intake/cases
    Note over Provider,IR: body: member_id, provider_id, cpt_code, icd10_code, service_type, requested_date, policy_id
    IR->>PG: INSERT Case with status=pending_verification
    IR->>Provider: case_id

    Provider->>IR: POST /api/v1/intake/cases/id/documents (multipart PDF/Scan/Fax)
    IR->>MINIO: PUT pa-case-documents/case_id/doc_id.pdf
    IR->>PG: INSERT Document with storage_path = MinIO key
    IR->>BG: asyncio.create_task run_completeness_pipeline(case_id)
    IR->>Provider: document_id
```

---

## Phase 2 — Policy Intake via Agent 1

```mermaid
sequenceDiagram
    participant ADM as Admin UI
    participant A1 as Agent 1 IntakeClassificationAgent
    participant PDF as pdf_service
    participant OLLAMA as Ollama LLM
    participant PG as PostgreSQL

    ADM->>A1: POST /api/v1/admin/policies with PDF upload
    A1->>PDF: extract_text_from_pdf(bytes)
    PDF->>A1: raw_text all pages
    A1->>OLLAMA: POST /v1/chat/completions
    Note over A1,OLLAMA: system_prompt + few-shot examples + policy_text
    OLLAMA->>A1: JSON array of description + matching_criteria
    Note over A1,OLLAMA: matching_criteria has keywords, time_window_months, notes
    A1->>PG: INSERT Policy + PolicyRequirements list
    A1->>ADM: policy_id and requirement_count
```

---

## Phase 3 — Completeness Pipeline (Agents 2 and 3)

```mermaid
sequenceDiagram
    participant CP as completeness_pipeline
    participant MINIO as MinIO
    participant PDF as pdf_service
    participant CHK as chunking_service
    participant A2 as Agent 2 EvidenceRetrievalAgent
    participant TEI as TEI Embeddings
    participant QD as Qdrant pa-evidence
    participant FUS as fusion_service
    participant A3 as Agent 3 PolicyReasoningAgent
    participant OLLAMA as Ollama LLM
    participant PG as PostgreSQL

    Note over CP: Triggered as background task on document upload

    CP->>PG: SELECT Case + Documents + PolicyRequirements

    loop For each uploaded Document
        CP->>MINIO: GET file at storage_path
        MINIO->>CP: raw PDF bytes
        CP->>PDF: extract_text_from_pdf(bytes)
        PDF->>CP: pages as list of strings
        CP->>CHK: chunk_pages(pages, case_id, doc_id)
        CHK->>CP: TextChunk list with sliding window and 50-token overlap
        CP->>A2: index_case_document(case_id, doc_id, pages)
        A2->>TEI: POST /embed with chunk texts
        TEI->>A2: dense vectors 1024-dim
        A2->>QD: upsert points with dense, sparse BM25, and payload
        Note over A2,QD: payload includes case_id, doc_id, chunk_id, page_number, text
    end

    loop For each PolicyRequirement
        CP->>A2: retrieve(case_id, requirements)
        A2->>TEI: POST /embed with query text
        TEI->>A2: query dense vector
        A2->>QD: search_dense(query_vec, filter=case_id, top_k=20)
        QD->>A2: ScoredPoint list dense results
        A2->>QD: search_sparse(sparse_query, filter=case_id, top_k=20)
        QD->>A2: ScoredPoint list BM25 results
        A2->>FUS: reciprocal_rank_fusion(dense, sparse, top_k=10)
        FUS->>A2: FusedResult list with keyword_miss flags
    end

    CP->>A3: assess_requirements with RequirementContext list

    loop For each Requirement
        A3->>OLLAMA: POST /v1/chat/completions
        Note over A3,OLLAMA: requirement description + evidence chunks + scoring prompt
        OLLAMA->>A3: confidence_score 0.0 to 1.0 and reasoning_summary
        Note over A3: Guardrails: above 0.80 = Present, 0.50 to 0.80 = Unclear, below 0.50 = Absent
        Note over A3: keyword_miss on identifier-based requirement forces Unclear
        A3->>CP: ReasoningResult with status, confidence, matched_doc_id, reasoning_log
    end

    CP->>PG: INSERT CompletenessReportItem for each requirement
    CP->>PG: UPDATE Case SET review_status=in_nurse_review and entered_review_at=NOW()
```

---

## Phase 4 — Nurse Review and Human Decision

```mermaid
sequenceDiagram
    participant NURSE as Nurse NurseReviewWorkspace
    participant RR as review_routes
    participant PG as PostgreSQL
    participant A4 as Agent 4 ReviewerSummaryAgent
    participant OLLAMA as Ollama LLM

    NURSE->>RR: GET /api/v1/review/cases with status=in_nurse_review
    RR->>PG: SELECT Cases WHERE review_status=in_nurse_review
    PG->>RR: Case list with policy_title
    RR->>NURSE: ReviewCaseList

    NURSE->>RR: GET /api/v1/review/cases/id
    RR->>PG: SELECT Case + CompletenessReportItems + PolicyRequirements
    PG->>RR: Case detail and completeness report
    RR->>NURSE: ReviewCaseOut with completeness_items

    NURSE->>RR: POST /api/v1/review/cases/id/claim
    RR->>PG: UPDATE Case SET claimed_by_id=nurse_id WHERE claimed_by_id IS NULL
    Note over RR: Atomic conditional UPDATE. Returns 409 if already claimed.

    opt Nurse overrides a checklist item
        NURSE->>RR: POST /api/v1/review/cases/id/checklist/item_id/override
        Note over NURSE,RR: body: overridden_status, override_reason
        RR->>PG: UPDATE CompletenessReportItem SET overridden_status, overridden_by_id, overridden_at
        RR->>PG: INSERT AuditLog with action_type=checklist_override
    end

    NURSE->>RR: POST /api/v1/review/cases/id/decision
    Note over NURSE,RR: body: decision = accept or return_to_provider, reason
    RR->>PG: Verify caller equals claimed_by_id else return 403

    alt Decision is Accept
        RR->>PG: UPDATE Case SET review_status=accepted and decided_by_id and decision_at
        RR->>PG: INSERT AuditLog with action_type=case_accepted
        RR->>NURSE: decision recorded
    else Decision is Return to Provider
        RR->>PG: UPDATE Case SET review_status=returned_to_provider
        RR->>PG: INSERT AuditLog with action_type=case_returned
        RR->>A4: draft_provider_communication(RejectionContext)
        A4->>OLLAMA: POST /v1/chat/completions
        Note over A4,OLLAMA: gap_items + nurse_notes + letter_prompt
        OLLAMA->>A4: draft letter text
        A4->>RR: SummaryAgentResult with draft_communication and status=DRAFT
        Note over A4: Draft is NEVER auto-sent. Requires nurse or admin approval.
        RR->>NURSE: decision_recorded and draft_communication
    end
```

---

## Phase 5 — SLA Escalation and Agent 5 Readiness

```mermaid
sequenceDiagram
    participant SLA as sla_service asyncio loop every 300s
    participant PG as PostgreSQL
    participant A5 as Agent 5 WorkflowAgent
    participant HP as health/readiness endpoint

    loop Every 5 minutes
        SLA->>PG: SELECT Cases WHERE review_status=in_nurse_review
        PG->>SLA: cases list
        loop For each case
            SLA->>PG: SELECT Policy.sla_hours for this case
            Note over SLA: Compare hours since entered_review_at vs sla_hours (default 48h)
            alt SLA Breached
                SLA->>PG: UPDATE Case SET assigned_queue=escalation_manager and claimed_by_id=NULL
                SLA->>PG: INSERT AuditLog with action_type=sla_escalation
            end
        end
    end

    HP->>A5: GET /health/readiness
    A5->>OLLAMA: GET /api/tags
    Note over A5,OLLAMA: OLLAMA is referenced as Ollama :11434
    A5->>TEI: GET /health
    Note over A5,TEI: TEI is referenced as TEI :8080
    A5->>QDRANT: GET /healthz
    Note over A5,QDRANT: Qdrant is referenced as Qdrant :6333
    A5->>MINIO2: GET /minio/health/live
    Note over A5,MINIO2: MinIO is referenced as MinIO :9000
    A5->>HP: ReadinessReport with all_healthy and services list
```

---

## Data Models (Entity Relationships)

```mermaid
erDiagram
    Policy {
        uuid id PK
        string title
        string cpt_code
        int sla_hours
        datetime created_at
    }

    PolicyRequirement {
        uuid id PK
        uuid policy_id FK
        string description
        json matching_criteria
        int seq
    }

    Case {
        uuid id PK
        string member_id
        string provider_id
        string cpt_code
        string icd10_code
        string service_type
        datetime requested_date
        uuid policy_id FK
        enum review_status
        enum assigned_queue
        uuid claimed_by_id
        datetime entered_review_at
        uuid decided_by_id
        string decision_reason
        datetime decision_at
        datetime created_at
    }

    Document {
        uuid id PK
        uuid case_id FK
        enum document_type
        string storage_path
        datetime uploaded_at
    }

    CompletenessReportItem {
        uuid id PK
        uuid case_id FK
        uuid policy_requirement_id FK
        enum status
        float confidence_score
        uuid matched_document_id
        uuid matched_chunk_id
        text reasoning_log
        enum overridden_status
        uuid overridden_by_id
        datetime overridden_at
        datetime created_at
    }

    AuditLog {
        uuid id PK
        uuid case_id FK
        string action_type
        uuid actor_id
        json payload
        datetime created_at
    }

    Policy ||--o{ PolicyRequirement : "has requirements"
    Case }o--|| Policy : "locked at submission"
    Case ||--o{ Document : "contains"
    Case ||--o{ CompletenessReportItem : "has report items"
    PolicyRequirement ||--o{ CompletenessReportItem : "assessed by"
    Case ||--o{ AuditLog : "generates events"
```

---

## Case Lifecycle State Machine

```mermaid
stateDiagram-v2
    [*] --> pending_verification : Provider submits PA case

    pending_verification --> in_nurse_review : Completeness pipeline complete. Agents 2 and 3 done. Report persisted.

    in_nurse_review --> accepted : Nurse clicks Accept
    in_nurse_review --> returned_to_provider : Nurse clicks Reject. Agent 4 drafts provider letter.
    in_nurse_review --> escalation_queue : SLA breached after 48h. claimed_by_id cleared.

    escalation_queue --> accepted : Escalation manager accepts
    escalation_queue --> returned_to_provider : Escalation manager rejects

    accepted --> [*]
    returned_to_provider --> [*]
```

---

## Qdrant Vector Store — Internal Structure

```
Collection: pa-evidence
│
├── Dense vectors  (name="dense", 1024-dim, Cosine distance)
│   └── Source: TEI server / BAAI/bge-large-en-v1.5
│
├── Sparse vectors (name="sparse", BM25 native Qdrant)
│   └── Use: keyword / identifier exact-match retrieval
│
└── Payload per indexed point:
    ├── case_id       — partitions all queries to current case only
    ├── document_id   — links back to Document ORM row
    ├── chunk_id      — stable UUID for SEC-004 audit citation
    ├── page_number   — shown in nurse UI for source citation
    └── text          — raw chunk text returned with search results
```

---

## Five-Agent Summary

| # | Agent | Class | Calls LLM | Key Input | Key Output |
|---|-------|-------|-----------|-----------|------------|
| 1 | Intake and Classification | `IntakeClassificationAgent` | Ollama | Policy PDF text | `PolicyRequirement[]` with description and matching_criteria |
| 2 | Evidence Retrieval RAG | `EvidenceRetrievalAgent` | TEI embeddings | `RequirementQuery[]` + case_id | `RetrievalAgentResult` — fused chunks with keyword_miss flags |
| 3 | Policy Reasoning and Gap Analysis | `PolicyReasoningAgent` | Ollama | Evidence chunks per requirement | `ReasoningResult[]` — Present / Absent / Unclear + confidence + reasoning_log |
| 4 | Reviewer Summary and Communication | `ReviewerSummaryAgent` | Ollama | Rejection context + gap items | `SummaryAgentResult` — DRAFT letter, never auto-sent |
| 5 | Workflow and Audit | `WorkflowAgent` | None — probes only | Case state | `RoutingDecision` + `ReadinessReport` |

---

## Confidence Threshold Guardrails (Agent 3)

```
LLM confidence score (0.0 to 1.0)
         |
         |-- above 0.80  ----------->  Present   (evidence found)
         |
         |-- 0.50 to 0.80  -------->  Unclear   (forces human nurse review)
         |
         |-- below 0.50  ---------->  Absent    (evidence not found)

SPECIAL RULE — keyword_miss guardrail:
  For identifier-based requirements (member_id, CPT, HCPCS, ICD-10):
  If BM25/keyword search returned NO hit (keyword_miss = True),
  result is forced to Unclear regardless of dense confidence score.

Nurse override:
  Nurse may set overridden_status on any checklist item.
  Original "status" column is NEVER mutated after creation.
  Every override is written to AuditLog (action_type=checklist_override).
```

---

## API Route Map

| Router | Prefix | Key Endpoints | Purpose |
|--------|--------|---------------|---------|
| `intake_routes` | `/api/v1/intake` | `POST /cases`, `POST /cases/{id}/documents` | Case submission and document upload |
| `review_routes` | `/api/v1/review` | `GET /cases`, `GET /cases/{id}`, `POST /cases/{id}/claim`, `POST /cases/{id}/decision`, `POST /cases/{id}/checklist/{item_id}/override` | Nurse review workflow |
| `ops_routes` | `/api/v1/ops` | `GET /dashboard`, `GET /queue-stats` | Operations dashboard data |
| `audit_routes` | `/api/v1/audit` | `GET /cases/{id}/log`, `GET /log` | Audit trail queries |
| `admin_routes` | `/api/v1/admin` | `POST /policies`, `GET /policies` | Policy management — admin only |
| `document_routes` | `/api/v1/documents` | `GET /documents/{id}` | Document retrieval |
| Root | `/health` | `GET /health`, `GET /health/readiness` | Liveness and readiness probes |

---

## Infrastructure Services Map

| Service | Container | Port | Role | Key Constraint |
|---------|-----------|------|------|----------------|
| PostgreSQL 16 | `pa_postgres` | 5433 | Relational store — workflow state, case data, audit log | All state changes go through SQLAlchemy ORM |
| MinIO | `pa_minio` | 9000 / 9001 console | S3-compatible object storage for raw document files | Bucket `pa-case-documents`, no public access |
| Qdrant v1.9.4 | `pa_qdrant` | 6333 HTTP / 6334 gRPC | Vector database — dense + sparse indexes per case | All queries filtered by `case_id` payload |
| Ollama | `pa_ollama` | 11434 | Local open-weight LLM host — llama3.1 default | External URLs blocked by `_is_external_url()` guard |
| TEI HuggingFace | `pa_tei` | 8080 | Local embedding inference — BAAI/bge-large-en-v1.5, 1024-dim | Local only. GPU variant available via image swap |

---

## Constitution Compliance

| Section | Rule | Enforced By |
|---------|------|-------------|
| §I — No Automated Decisions | Agents output Present/Absent/Unclear only. Nurses alone Accept/Reject. | `review_routes` returns 403 if not claimant. `review_status` never auto-set to `accepted`. |
| §II — Local Inference Only | All LLM and embedding calls go to Ollama/TEI on localhost only. | `_is_external_url()` guard in WorkflowAgent. Secrets abstraction for all endpoints. |
| §IV — Full Audit Trail | Every agent action logged. `reasoning_log` stored per completeness item. | `AuditLog` model. `log_audit_event()` called on claim, decision, override, SLA escalation. |
| §V — Secrets Abstraction | No hardcoded URLs or credentials anywhere. | All endpoints via `get_secret()` and `require_secret()` from `core/secrets.py`. |
