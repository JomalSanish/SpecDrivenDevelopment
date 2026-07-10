# Tasks: pa-evidence-assistant

**Input**: Design documents from `specs/001-pa-evidence-assistant/`

**Organization**: Tasks are grouped by the specific multi-phase dependency graph outlined in the project requirements.

## Format: `[ID] [P?] [Story] Description`
- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)

---

## Phase 1: Foundation, secrets-manager abstraction, local embedding/LLM serving stubs (Phase 1)

**Purpose**: Core infrastructure and abstracted credential management.

- [X] T001 Initialize FastAPI backend and React frontend projects
- [X] T002 [P] Setup PostgreSQL database schema using Alembic (`backend/src/models/core.py`)
- [X] T003 [P] Implement HashiCorp Vault secrets-manager abstraction (`backend/src/core/secrets.py`)
- [X] T004 Deploy local MinIO instance via docker-compose and configure bucket for isolated case documents (`infrastructure/minio/`)
- [x] T005 [FLAG: Network Egress Warning - MUST strictly use local models] Setup local `Ollama` service for open-weight LLM inference (`docker-compose.yml` — `ollama` service)
- [X] T006 [FLAG: Network Egress Warning - MUST strictly use local models] Setup local `TEI/SentenceTransformers` endpoint for embeddings (`infrastructure/llm_serving/embeddings-compose.yml`)
- [X] T007 Deploy local Qdrant vector store (`infrastructure/qdrant/`)

---

## Phase 2: Document ingestion, policy parsing, requirement-checklist extraction (Phase 2)

**Purpose**: Admin policy ingestion and case document uploading.

- [ ] T008 [US1] Create `Policy` and `PolicyRequirement` models in `backend/src/models/policy.py`, including the optional `sla_hours` field on `Policy` used by the SLA escalation task (T031)
- [ ] T009 [US1] Implement Admin Policy Ingestion endpoint `POST /api/v1/admin/policies` (`backend/src/api/admin_routes.py`)
- [ ] T010 [US1] Build Intake & Classification Agent to parse policy requirements (`backend/src/agents/intake_agent.py`)
- [ ] T011 [US2] Create `Case` and `Document` models in `backend/src/models/case.py`, matching `data-model.md` exactly — including `assigned_queue` as an Enum (not free-text String) and the `entered_review_at` timestamp used by the SLA escalation task (T031)
- [ ] T012 [US2] Implement Intake endpoint `POST /api/v1/intake/cases` (`backend/src/api/intake_routes.py`)
- [ ] T013 [P] [US1] Implement React Intake Dashboard UI components (`frontend/src/pages/IntakeDashboard.tsx`)

---

## Phase 3: Hybrid RAG indexing and retrieval (dense + sparse + fusion) (Phase 3)

**Purpose**: Indexing and Retrieval engine.

- [ ] T014 [US2] Create Qdrant indexing service with strictly partitioned `case_id` payload filters (`backend/src/services/qdrant_service.py`)
- [ ] T015 [US2] Implement semantic sentence chunking (512 tokens, 50 token overlap) (`backend/src/services/chunking_service.py`)
- [ ] T016 [US2] Build Evidence Retrieval (RAG) Agent (`backend/src/agents/retrieval_agent.py`)
- [ ] T017 [US2] Implement Reciprocal Rank Fusion (RRF) for dense + sparse BM25 vectors (`backend/src/services/fusion_service.py`)

---

## Phase 4: Completeness verification pipeline (Present/Absent/Unclear classification) (Phase 4)

**Purpose**: Agentic evaluation of required documents against uploaded evidence.

- [ ] T018 [US2] Create `CompletenessReportItem` model in `backend/src/models/completeness.py`
- [ ] T019 [US2] Build Policy Reasoning & Gap Analysis Agent (`backend/src/agents/reasoning_agent.py`)
- [ ] T020 [US2] Enforce confidence threshold guardrails (>80% Present, 50-80% Unclear, <50% Absent) in `reasoning_agent.py`
- [ ] T021 [US2] Build Reviewer Summary & Communication Agent to draft rejection notes (`backend/src/agents/summary_agent.py`)

---

## Phase 5: Nurse Review UI — document viewer, completeness report display, Accept/Reject actions (Phase 5)

**Purpose**: Human-in-the-loop application interface.

- [ ] T022 [US3] Implement `GET /api/v1/review/cases` and `GET /api/v1/review/cases/{case_id}` endpoints (`backend/src/api/review_routes.py`)
- [ ] T023 [US3] Implement strict locking endpoint `POST /api/v1/review/cases/{case_id}/claim` using an atomic conditional update (`UPDATE cases SET claimed_by_id = :nurse_id WHERE id = :case_id AND claimed_by_id IS NULL`, rejecting the claim with a 409 Conflict if rows-affected == 0) — not a read-then-write check, to avoid a race between two nurses claiming the same case (`backend/src/api/review_routes.py`)
- [ ] T024 [US3] Implement Nurse decision endpoint `POST /api/v1/review/cases/{case_id}/decision` ensuring structured reason codes; maps the nurse-facing `action` field (`Accept`|`Reject`) to `review_status` values `accepted`|`returned_to_provider` respectively — there is no separate `rejected` state, since Reject always means "sent back to the provider for more documentation," never a terminal denial; reject with 403 Forbidden if the requesting nurse's ID does not match `claimed_by_id` on the case (no claim, or claimed by someone else), so a decision can only be recorded by the nurse currently holding the lock from T023 (`backend/src/api/review_routes.py`)
- [ ] T025 [P] [US3] Build React Nurse Review Workspace UI (`frontend/src/pages/NurseReviewWorkspace.tsx`)
- [ ] T026 [P] [US3] Integrate in-app PDF Document Viewer into Nurse Workspace (`frontend/src/components/DocumentViewer.tsx`)
- [ ] T027 [P] [US3] Implement override buttons for system-generated checklist items (`frontend/src/components/CompletenessChecklist.tsx`)

---

## Phase 6: Multi-agent orchestration and audit logging across all 5 agents (Phase 6)

**Purpose**: End-to-end routing and compliance tracing.

- [ ] T028 [US4] Create `AuditLog` model in `backend/src/models/audit.py`
- [ ] T029 [US4] Build Workflow/Audit & Deployment Readiness Agent (`backend/src/agents/workflow_agent.py`)
- [ ] T030 [US4] Implement database transaction logger wrapping all RAG and LLM prompts (`backend/src/core/logger.py`)
- [ ] T031 [US5] Implement SLA escalation timer to re-route cases after timeout, computed from `Case.entered_review_at` against `Policy.sla_hours` (falling back to a global default if unset); on breach, set `assigned_queue` to `escalation_manager` and clear `claimed_by_id` so the case leaves the original nurse's queue (`backend/src/services/sla_service.py`)
- [ ] T032 [P] [US4] Build Operations Dashboard UI to view audit logs (`frontend/src/pages/OperationsDashboard.tsx`)

---

## Phase 7: Automated tests derived from specs (Phase 7)

**Purpose**: Validate functional and non-functional requirements.

- [ ] T033 [P] Write integration tests for Admin Policy Ingestion (`backend/tests/integration/test_admin.py`)
- [ ] T034 [P] Write tests verifying `case_id` strict partitioning in Qdrant (`backend/tests/integration/test_qdrant.py`)
- [ ] T035 [P] Write tests verifying Nurse Review explicit state fields (no automated decisions) (`backend/tests/integration/test_workflow.py`)
- [ ] T036 [P] Write tests for confidence threshold edge cases (`backend/tests/unit/test_reasoning_agent.py`)
- [ ] T037 [P] Write React component tests for Nurse Review UI (`frontend/tests/components/NurseReview.test.tsx`)

---

## Phase 8: CI/CD, encryption/TLS hardening, deployment readiness checks (Phase 8)

**Purpose**: Deployment pipeline and final security validations.

- [ ] T038 Create GitHub Actions / GitLab CI pipeline (`.github/workflows/deploy.yml`)
- [ ] T039 [FLAG: AST Public API Check] Implement custom Semgrep/AST script to fail build if public LLM APIs (`openai.com`, `anthropic.com`) are called (`scripts/security_check.py`)
- [ ] T040 Implement Secrets Scanning (TruffleHog) in CI pipeline
- [ ] T041 Configure Kubernetes Helm charts for blue/green deployment (`infrastructure/helm/`)
- [ ] T042 Enforce TLS for internal service-to-service communication (`infrastructure/helm/templates/`)

---

## Dependencies & Execution Order
- Phase 1 must be complete before any other phase begins.
- Phase 2 (Ingestion) blocks Phase 3 and Phase 4.
- Phase 3 (Indexing) blocks Phase 4.
- Phase 4 (Completeness) blocks Phase 5.
- Phase 6 (Logging) runs concurrently with all agent implementations.
- Phase 7 (Testing) and Phase 8 (Deploy) conclude the workflow.
