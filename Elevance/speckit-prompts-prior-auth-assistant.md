# Spec-Kit Prompt Playbook
## Prior Authorization Evidence Assistant (Elevance Use Case)

This maps your 10 required specifications onto GitHub Spec-Kit's actual command flow, then gives you a ready-to-paste, elaborate prompt for every stage. Current Spec-Kit workflow (namespace `/speckit.*`):

```
/speckit.constitution → /speckit.specify → /speckit.clarify → /speckit.plan
     → /speckit.checklist → /speckit.tasks → /speckit.analyze → /speckit.implement
```

### How your 10 required specs map to Spec-Kit artifacts

| # | Required Spec (from use case doc) | Spec-Kit Stage | Output File |
|---|---|---|---|
| 1 | Requirement specification | `/speckit.specify` | `spec.md` |
| 2 | Architecture specification | `/speckit.plan` | `plan.md` |
| 3 | Data specification | `/speckit.plan` | `data-model.md` |
| 4 | API specification | `/speckit.plan` | `contracts/*.yaml` |
| 5 | Agent specification | `/speckit.plan` (custom artifact) | `agent-spec.md` |
| 6 | RAG pipeline specification | `/speckit.plan` (custom artifact) | `rag-pipeline.md` |
| 7 | UI specification | `/speckit.plan` (custom artifact) | `ui-spec.md` |
| 8 | Test specification | `/speckit.tasks` + `/speckit.checklist` | `tasks.md`, `checklists/*.md` |
| 9 | Security & compliance specification | `/speckit.constitution` + `/speckit.plan` | `constitution.md`, `security-compliance.md` |
| 10 | CI/CD & deployment specification | `/speckit.plan` (custom artifact) | `cicd-deployment.md` |

Run `specify init prior-auth-evidence-assistant --ai claude` first, then work through the stages below in order. Don't skip `/speckit.clarify` or `/speckit.analyze` on a project with this much regulatory sensitivity — they're your two cheapest bug-catchers.

---

## Stage 1 — `/speckit.constitution`

This is where your "no automated approval/denial" and compliance constraints become non-negotiable, enforced at every later gate.

```
/speckit.constitution

This project is the Prior Authorization Evidence Assistant, a human-in-the-loop
evidence preparation and operational triage system for a healthcare payer.
Establish the following as non-negotiable governing principles:

1. HUMAN-IN-THE-LOOP ONLY: The system must never approve, deny, or make a final
   clinical or coverage determination. Every agent that touches medical necessity
   (Policy Reasoning & Gap Agent) must output a "human_review_required" flag and
   may only label evidence as present/absent/unclear or ambiguous — never
   "approved" or "denied". Any code path that could be interpreted as an automated
   decision must be rejected at review time.

2. GROUNDED, CITED OUTPUTS ONLY: No agent may generate a clinical or policy claim
   without a traceable citation to a source document, chunk ID, and confidence
   score. If retrieval confidence falls below a defined threshold, the system must
   return "Insufficient Evidence" rather than fabricate an answer. Unsupported
   answers are treated as a critical defect.

3. FULL AUDITABILITY: Every agent invocation must be logged with: agent name,
   input hash, model + version, prompt version, retrieved source IDs, confidence
   score, output, and timestamp. Logs are immutable/append-only and must be
   queryable by case_id for the Auditor and QA/Test Engineer personas.

4. NO REAL PHI IN DEVELOPMENT: All development, testing, and CI environments use
   synthetic member/provider/clinical data only. Any ingestion pathway must
   support a "synthetic mode" flag, and real PHI ingestion is out of scope for
   this build.

5. SECURITY BY DEFAULT: Role-based access control aligned to the 7 personas
   (Intake Associate, Nurse Reviewer, Medical Director, Provider Relations,
   Operations Manager, Auditor, QA/Test Engineer). Encryption in transit (TLS 1.2+)
   and at rest (AES-256) for all documents, embeddings, and case metadata. Secrets
   must never be hard-coded; use a secrets manager abstraction from day one.

6. TESTABILITY: Every functional requirement in spec.md must be traceable to at
   least one automated test. Adversarial cases (no evidence found, contradictory
   evidence, low-confidence retrieval, incomplete case) are first-class test
   scenarios, not edge cases added later.

7. EXPLAINABILITY: Every routing decision and gap determination must include a
   short natural-language rationale a nurse or medical director can read without
   needing to inspect logs.

8. ARCHITECTURE GOVERNANCE: The system is composed of 5 specialized agents
   orchestrated around a shared case state and a RAG knowledge layer. Agents are
   independently deployable services with versioned prompts and versioned
   knowledge bases. Breaking changes to an agent's input/output contract require
   a version bump and backward-compatible fallback.

Amendments to these principles require explicit justification recorded in the
constitution's changelog; they cannot be silently overridden by a later plan or
task.
```

---

## Stage 2 — `/speckit.specify`

Keep this to *what* and *why* — no tech stack. Feed it the requirement spec, personas, and sample interactions directly from your use-case document so the acceptance scenarios are already locked in.

```
/speckit.specify

Build the Prior Authorization Evidence Assistant: a RAG-and-multi-agent system
that helps healthcare payer operations staff prepare and triage prior
authorization (PA) cases — it does NOT make clinical approval/denial decisions.

BUSINESS CONTEXT
Payer operations teams manually review provider-submitted PA requests (imaging,
drugs, surgeries, DME, specialty services) against medical policy, benefit rules,
and clinical documentation to decide whether a case is complete, whether
supporting evidence exists, and where it should be routed (nurse review, medical
director review, or additional-documentation follow-up). This assistant
automates evidence retrieval, gap detection, summarization, and routing —
leaving every clinical judgment to a human.

TARGET USERS AND THEIR NEEDS
- Prior Authorization Intake Associate: completeness checks, missing-document
  detection at case creation.
- Nurse Reviewer: clinical summary, policy-to-case evidence mapping, gap
  analysis with citations.
- Medical Director: concise case brief with supporting facts for escalated cases.
- Provider Relations User: neutral, provider-facing explanation of what
  documentation is missing and why.
- Operations Manager: queue-level insight into routing accuracy, backlog, and
  SLA risk.
- Compliance/Audit User: full source citations, audit trail, and prompt/model
  logs per case.
- QA/Test Engineer: predictable, well-defined behavior for failure modes
  (no evidence found, contradictory evidence).

FUNCTIONAL REQUIREMENTS
1. Ingest a PA case: member demographics, provider-submitted clinical notes,
   diagnosis (ICD-10) and procedure (CPT/HCPCS) codes, benefit plan rules, prior
   authorization history, and attachments (PDF, fax, scanned documents, referral
   forms).
2. Classify the case by request type (imaging, surgery, drug, DME, behavioral
   health, specialty referral) and determine completeness; flag possible
   duplicates.
3. Retrieve relevant evidence from medical policy documents, benefit plan
   documents, PA criteria, and the case's own submitted documents, returning
   citations and confidence scores for every retrieved item.
4. Compare retrieved evidence against policy criteria in checklist form; label
   each criterion as present, absent, or unclear; identify missing documentation;
   escalate ambiguous or contradictory findings — without ever issuing an
   approve/deny determination.
5. Generate human-readable outputs: case summary, evidence table, missing-
   document request draft (provider-facing, neutral tone), reviewer checklist,
   and escalation note.
6. Route the case to the correct queue (Intake, Nurse Review, Medical Director
   Review) with a stated reason and confidence score.
7. Maintain a full audit trail per case: which agent did what, which sources
   were used, prompt/model versions, and confidence scores, retrievable on
   demand by an Auditor.
8. Provide a reviewer dashboard showing case status, queue, and the outputs
   above, with drill-down into evidence and citations.

IN SCOPE: case ingestion, document upload and parsing, OCR integration
placeholder, metadata capture, RAG retrieval, 5-agent orchestration, case
summarization, missing-info detection, policy evidence mapping, human-in-the-
loop review workflow, reviewer dashboard, audit log, deployment pipeline,
spec-derived automated tests.

OUT OF SCOPE: automated medical approval/denial, final clinical decisioning,
production integration with real payer systems (mocked only), real PHI in
development, payment/claims adjudication, regulatory/legal determinations.

ACCEPTANCE SCENARIOS (representative — treat each as a testable user story)
- Given a new imaging PA request, when an Intake Associate creates the case,
  then the system returns a structured case_id, status "Created", request_type
  "Advanced Imaging", and a "next_step" of uploading documents.
- Given an incomplete case, when the Intake Associate asks what's missing, then
  the system returns the specific missing fields (e.g., clinical notes, prior
  therapy records) and a case_status of "Incomplete".
- Given uploaded documents, when a Nurse Reviewer asks what evidence supports
  the request, then the system returns retrieved evidence with source name,
  matched text, and a confidence score, never an unsupported claim.
- Given retrieved evidence, when a Nurse Reviewer asks if there's enough
  evidence for review, then the system returns a per-criterion status
  (present/missing) and a human_review_required flag of true — never a decision.
- Given no relevant evidence is found, when any user queries the case, then the
  system returns a clear "Insufficient Evidence" status and recommends escalation
  to manual review rather than guessing.
- Given contradictory evidence, when the Policy Reasoning & Gap Agent evaluates
  the case, then the system flags "Ambiguous Evidence" with conflict_detected
  true and recommends human clinical review.
- Given a routed case, when an Operations Manager asks which queue a case should
  go to, then the system returns the routing decision, a stated reason, and a
  confidence score.
- Given a completed case, when an Auditor requests the audit trail, then the
  system returns a full agent-by-agent action log with timestamps and sources
  used for any generated summary.

SUCCESS CRITERIA: every generated clinical/policy statement is traceable to a
cited source; every case has a complete, queryable audit trail; no code path can
emit an approval or denial; intake completeness checks catch missing
documentation before a case reaches a nurse queue.
```

---

## Stage 3 — `/speckit.clarify`

Just run the command — it asks up to ~5 sequential questions and writes answers back into `spec.md`. Given the compliance sensitivity here, expect it to probe on things like document formats, retention, thresholds, and vendor choices. Have your answers ready:

```
/speckit.clarify
```

**Likely questions and suggested answers to give when prompted:**
- *OCR/document parsing engine?* → "Use a placeholder/mock OCR interface for now (e.g., an abstraction that could later wrap Textract or Azure Form Recognizer); do not integrate a real OCR vendor in this phase."
- *Vector database / embedding model?* → "Use pgvector on Postgres for the vector index and a swappable embedding provider interface so the model can be changed without touching agent logic."
- *LLM provider for agents?* → "Use the Anthropic API (Claude) via a provider-agnostic interface so the underlying model can be swapped."
- *Confidence score thresholds for escalation?* → "Below 0.6 confidence, auto-flag for manual review; between 0.6–0.8, surface with a caution indicator; above 0.8, present normally — all still human-reviewed."
- *Data retention / synthetic data policy?* → "All case and document data in dev/test is synthetic; retention policy for the audit log is indefinite (append-only) within this project's scope."
- *Authentication approach?* → "Role-based access control with 7 predefined personas; SSO integration is out of scope, use a mocked auth provider."

---

## Stage 4 — `/speckit.plan`

This single stage needs to produce your architecture, data, API, agent, RAG, and UI specs. Ask explicitly for the supplementary documents Spec-Kit doesn't generate by default (agent-spec.md, rag-pipeline.md, ui-spec.md, security-compliance.md, cicd-deployment.md) alongside the standard plan.md/data-model.md/contracts/.

```
/speckit.plan

TECH STACK
Backend: Python 3.12, FastAPI microservices — one service per agent plus a case
orchestration/API gateway service. Postgres 16 with the pgvector extension for
both relational case data and embeddings (avoid a separate vector DB unless
research shows a hard requirement). Async job queue (e.g., Celery or an async
task runner) for long-running ingestion/retrieval work. Frontend: React +
TypeScript reviewer dashboard using a component library appropriate for a
data-dense operations UI (tables, evidence panels, queue views). Containerize
every service with Docker; orchestrate with docker-compose for local dev and
document a Kubernetes-ready structure for production.

ARCHITECTURE SPECIFICATION (produce as plan.md)
Design a 5-agent architecture matching this pipeline: Provider Submission →
Case Intake API/UI → Intake & Classification Agent → Document Parser + OCR
(mocked) + Metadata Extractor → Vector Index + Policy Knowledge Base → Evidence
Retrieval RAG Agent → Policy Reasoning & Gap Agent → Reviewer Summary &
Communication Agent → Workflow, Audit & Deployment Readiness Agent → Human
Reviewer Dashboard → Feedback Capture + Spec Update Loop. Each agent is a
separately deployable FastAPI service communicating over an internal REST or
message-queue contract; document the orchestration pattern (sequential pipeline
with conditional branches for escalation) and the shared case-state store all
agents read/write against.

DATA SPECIFICATION (produce as data-model.md)
Model these entities at minimum: Case (case_id, member_id, provider_id, request
type, CPT/HCPCS codes, ICD-10 codes, status, confidence scores, created/updated
timestamps), Document (document_id, case_id, type, source, parsed text,
embedding refs), PolicyDocument (policy_id, section, text chunks, embeddings,
version), EvidenceItem (source, matched text, confidence, citation ref),
GapChecklistItem (criterion, status: present/absent/unclear, rationale),
RoutingDecision (case_id, queue, reason, confidence), AuditLogEntry (agent,
action, input hash, prompt version, model version, sources, timestamp,
case_id). Define relationships, required fields, and state transitions for
Case.status (Created → Intake Review → Ready for Evidence Review → Nurse Review
→ Medical Director Review → Awaiting Provider Documentation).

API SPECIFICATION (produce as contracts/ in OpenAPI format)
Define REST contracts for: Case Intake API (create/update case, upload
documents, get completeness status), Evidence Retrieval API (query evidence for
a case, query policy sections), Gap Analysis API (get criteria checklist, get
human_review_required flag), Summary API (generate case summary, missing-
document request draft, reviewer checklist, escalation note), Routing API
(get/set queue assignment), Audit API (get full agent log by case_id, get
sources used for a given output). All endpoints return structured JSON matching
the sample outputs in spec.md and never an approval/denial field.

AGENT SPECIFICATION (produce as agent-spec.md)
Document each of the 5 agents with: purpose, responsibilities, inputs, outputs,
knowledge sources, explicit constraints (especially: Policy Reasoning & Gap
Agent must never approve/deny), triggering conditions, and hand-off contract to
the next agent in the pipeline — matching the Intake & Classification, Evidence
Retrieval RAG, Policy Reasoning & Gap, Reviewer Summary & Communication, and
Workflow/Audit/Deployment Readiness agents described in the requirement spec.

RAG PIPELINE SPECIFICATION (produce as rag-pipeline.md)
Define: document chunking strategy (per policy section / per clinical note
paragraph), embedding generation and refresh strategy, hybrid (keyword +
semantic) search approach, citation format returned with every retrieved chunk,
a confidence-scoring method, and an explicit "no unsupported answer" fallback
(return Insufficient Evidence rather than hallucinate) plus contradictory-
evidence detection logic feeding the Policy Reasoning & Gap Agent.

UI SPECIFICATION (produce as ui-spec.md)
Design the reviewer dashboard: case queue views by role (Intake, Nurse, Medical
Director, Ops Manager, Auditor), a case detail view showing the evidence table
with citations, the gap checklist, generated summaries, routing status, and an
audit trail drill-down. Include accessibility requirements (WCAG 2.1 AA) and a
persona-based navigation model (each of the 7 personas sees a tailored view).

SECURITY & COMPLIANCE SPECIFICATION (produce as security-compliance.md)
Detail RBAC per persona, encryption in transit/at rest, secrets management,
synthetic-data-only policy for dev/test, audit log immutability, and a PHI-
handling boundary statement given production PHI integration is out of scope.

CI/CD AND DEPLOYMENT SPECIFICATION (produce as cicd-deployment.md)
Define a GitHub Actions pipeline: lint/type-check → unit tests → integration
tests (including the adversarial RAG/gap scenarios) → build container images →
deploy to a staging environment → manual gate → production deploy. Include a
deployment-readiness checklist matching the Workflow, Audit & Deployment
Readiness Agent's responsibilities.

Flag any area needing further research (e.g., specific hybrid search library,
specific OpenAPI tooling) explicitly in research.md rather than guessing.
```

---

## Stage 5 — `/speckit.checklist` (run 3 focused passes)

Checklists test whether your *requirements* are well-written, not whether the code works — run one per risk area rather than one giant generic list.

**Pass 1 — Security & Compliance**
```
/speckit.checklist

Generate a "Security & Compliance" checklist for the Prior Authorization
Evidence Assistant. For every requirement touching PHI handling, RBAC,
encryption, audit logging, and the "no automated approval/denial" constraint,
ask whether it is: (a) unambiguous, (b) measurable/testable, (c) traceable to a
specific constitution principle, and (d) free of any wording that could be read
as permitting an automated clinical decision. Flag any requirement that uses
vague terms like "secure" or "compliant" without a concrete, checkable
criterion.
```

**Pass 2 — RAG & Agent Reasoning Quality**
```
/speckit.checklist

Generate a "RAG & Agent Reasoning" checklist verifying that every requirement
about evidence retrieval, citation, confidence scoring, and gap analysis
specifies: what happens when no evidence is found, what happens when evidence
conflicts, the minimum citation metadata required per claim, and that no
requirement implicitly allows an unsupported (uncited) statement to reach a
reviewer.
```

**Pass 3 — UI & Reviewer Workflow**
```
/speckit.checklist

Generate a "Reviewer Experience" checklist covering the 7 personas. For each
persona, verify the spec defines exactly what they can see, what actions they
can take, what output format they receive (structured JSON vs. Markdown
summary), and that role boundaries (e.g., Provider Relations cannot see internal
audit logs) are explicit rather than assumed.
```

---

## Stage 6 — `/speckit.tasks`

```
/speckit.tasks

Break the plan into dependency-ordered, independently testable tasks. Group
tasks by: (1) foundation — repo scaffold, data model, Postgres+pgvector setup,
case orchestration API; (2) Intake & Classification Agent; (3) Document
ingestion + Evidence Retrieval RAG Agent (chunking, embeddings, hybrid search,
citation formatting); (4) Policy Reasoning & Gap Agent (checklist comparison,
present/absent/unclear labeling, ambiguity escalation — with an explicit test
task verifying it never emits an approve/deny field); (5) Reviewer Summary &
Communication Agent (case summary, evidence table, missing-doc draft, checklist,
escalation note generation); (6) Workflow, Audit & Deployment Readiness Agent
(routing logic, audit logging, deployment-readiness checks); (7) Reviewer
dashboard UI per persona; (8) security/RBAC implementation; (9) CI/CD pipeline;
(10) test suite, including the adversarial scenarios (no evidence found,
contradictory evidence, low-confidence retrieval, incomplete case) as explicit
tasks, not an afterthought. Mark tasks that can run in parallel with [P]. Map
every task back to a functional requirement or acceptance scenario in spec.md
so coverage can be verified.
```

---

## Stage 7 — `/speckit.analyze`

```
/speckit.analyze

Run a full cross-artifact consistency check across constitution.md, spec.md,
plan.md, data-model.md, contracts/, agent-spec.md, rag-pipeline.md, and
tasks.md. Specifically flag as CRITICAL: any task or contract that could allow
an automated approve/deny output, any generated-output path missing a citation
requirement, any requirement without a corresponding task, and any agent
responsibility in agent-spec.md not reflected in tasks.md. Report coverage
gaps, duplications, and ambiguities with severity ratings before I proceed to
implementation.
```

Fix everything CRITICAL/HIGH before moving on — this is the cheapest point to catch a compliance gap.

---

## Stage 8 — `/speckit.implement` (phased, not all at once)

Don't run the full task list unattended on a project this sensitive. Implement and validate in phases, reviewing after each.

**Phase 1 — Foundation**
```
/speckit.implement

Implement only the foundation tasks: repo scaffold, Postgres + pgvector schema
from data-model.md, and the Case Intake API with the Intake & Classification
Agent. Stop after this phase so I can review before continuing.
```

**Phase 2 — Evidence Retrieval**
```
/speckit.implement

Now implement the document ingestion pipeline and Evidence Retrieval RAG Agent:
chunking, embeddings, hybrid search, and citation-formatted responses,
including the "Insufficient Evidence" fallback path. Stop after this phase for
review.
```

**Phase 3 — Reasoning, Summarization, Workflow**
```
/speckit.implement

Implement the Policy Reasoning & Gap Agent, the Reviewer Summary &
Communication Agent, and the Workflow/Audit/Deployment Readiness Agent,
including the audit logging required by the constitution. Verify no code path
in the Gap Agent can emit an approval or denial value. Stop after this phase
for review.
```

**Phase 4 — UI, Security, CI/CD**
```
/speckit.implement

Implement the reviewer dashboard per ui-spec.md, apply RBAC per
security-compliance.md, and stand up the CI/CD pipeline per
cicd-deployment.md. Finish by running the full adversarial test suite (no
evidence found, contradictory evidence, low-confidence retrieval) and report
results.
```

---

### A few operating notes
- Keep `/speckit.clarify` and `/speckit.analyze` as mandatory gates here, not optional — a payer PA system is exactly the "meaningful ambiguity / production feature" case they're designed for.
- If your agent supports it, run `/speckit.taskstoissues` after `/speckit.tasks` to push the task list into GitHub Issues for team tracking.
- Re-run `/speckit.analyze` a second time after Phase 4 implementation as a final drift check against the constitution.
