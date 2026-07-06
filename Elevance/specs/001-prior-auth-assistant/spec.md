# Feature Specification: Prior Authorization Evidence Assistant

**Feature Branch**: `[NOT APPLICABLE]`

**Created**: 2026-07-06

**Status**: Draft

**Input**: User description: "Build the Prior Authorization Evidence Assistant: a RAG-and-multi-agent system that helps healthcare payer operations staff prepare and triage prior authorization (PA) cases..."

## Clarifications

### Session 2026-07-06

- Q: OCR/document parsing engine? → A: Placeholder/mock OCR interface wrapping Textract or Azure Form Recognizer.
- Q: Vector database / embedding model? → A: pgvector on Postgres with swappable embedding provider interface.
- Q: LLM provider for agents? → A: Anthropic API (Claude) via a provider-agnostic interface.
- Q: Confidence score thresholds for escalation? → A: <0.6 auto-flag for manual review; 0.6–0.8 caution; >0.8 present normally.
- Q: Data retention / synthetic data policy? → A: Synthetic dev/test data; indefinite audit log retention.
- Q: Authentication approach? → A: Mocked auth provider for RBAC with 7 personas (no SSO).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Case Intake and Completeness Check (Priority: P1)

An Intake Associate processes a new PA request and determines whether all required documentation is present.

**Why this priority**: Correctly classifying and detecting missing documents at case creation prevents downstream clinical reviewers from wasting time on incomplete cases. This is the entry point of the system.

**Independent Test**: Can be fully tested by submitting a mock PA request (complete and incomplete versions) and verifying the system's "status", "request_type", and "missing fields" outputs without involving clinical routing.

**Acceptance Scenarios**:

1. **Given** a new imaging PA request with all required attachments, **When** an Intake Associate creates the case, **Then** the system returns a structured case_id, status "Created", request_type "Advanced Imaging", and a "next_step" of uploading documents (or routing to review).
2. **Given** an incomplete case missing clinical notes, **When** the Intake Associate asks what's missing, **Then** the system returns the specific missing fields (e.g., clinical notes, prior therapy records) and a case_status of "Incomplete".

---

### User Story 2 - Clinical Evidence Retrieval and Gap Analysis (Priority: P1)

A Nurse Reviewer evaluates the case to see what evidence supports the request and if there are gaps compared to medical policy criteria.

**Why this priority**: This is the core value proposition of the RAG system: mapping policy to case evidence without making a decision.

**Independent Test**: Can be fully tested by feeding a complete PA case and policy document into the agent and validating the evidence table, citations, and confidence scores.

**Acceptance Scenarios**:

1. **Given** uploaded documents for a complete case, **When** a Nurse Reviewer asks what evidence supports the request, **Then** the system returns retrieved evidence with source name, matched text, and a confidence score, never an unsupported claim.
2. **Given** retrieved evidence mapped to policy, **When** a Nurse Reviewer asks if there's enough evidence for review, **Then** the system returns a per-criterion status (present/missing) — never a decision.

---

### User Story 3 - Insufficient Evidence Handling (Priority: P1)

The system gracefully handles cases where it cannot find relevant evidence to support the policy criteria.

**Why this priority**: Preventing hallucination is critical for clinical/medical workflows (Constitution Principle: GROUNDED, CITED OUTPUTS ONLY).

**Independent Test**: Can be fully tested by submitting a PA case with irrelevant attachments and ensuring the system fails safely.

**Acceptance Scenarios**:

1. **Given** no relevant evidence is found in the case documents, **When** any user queries the case, **Then** the system returns a clear "Insufficient Evidence" status and recommends escalation to manual review rather than guessing.

---

### User Story 4 - Contradictory Evidence Escalation (Priority: P2)

The system flags when submitted evidence is ambiguous or contradictory, escalating to a human for clinical judgment.

**Why this priority**: Protects against automated errors when medical records conflict.

**Independent Test**: Can be fully tested by submitting documents that both confirm and deny a specific condition.

**Acceptance Scenarios**:

1. **Given** contradictory evidence in the clinical notes, **When** the Policy Reasoning & Gap Agent evaluates the case, **Then** the system flags "Ambiguous Evidence" with conflict_detected true and recommends human clinical review.

---

### User Story 5 - Automated Queue Routing (Priority: P2)

An Operations Manager relies on the system to route cases to the correct queue (Intake, Nurse, MD) with a stated rationale.

**Why this priority**: Improves operational efficiency and SLA adherence.

**Independent Test**: Can be fully tested by evaluating routing decisions on a batch of mock cases.

**Acceptance Scenarios**:

1. **Given** a routed case, **When** an Operations Manager asks which queue a case should go to, **Then** the system returns the routing decision, a stated reason, and a confidence score.

---

### User Story 6 - Audit Trail and Compliance Verification (Priority: P3)

An Auditor or QA Engineer reviews the detailed system logs to verify compliance, agent behavior, and citations.

**Why this priority**: Mandated by the project constitution (FULL AUDITABILITY).

**Independent Test**: Can be fully tested by pulling the audit log for a completed case and verifying all required fields (hash, model, sources, timestamps) exist.

**Acceptance Scenarios**:

1. **Given** a completed case, **When** an Auditor requests the audit trail, **Then** the system returns a full agent-by-agent action log with timestamps and sources used for any generated summary.

## Edge Cases

- What happens when a submitted PDF is corrupted, password-protected, or unreadable by the OCR placeholder?
- How does the system handle cases where the retrieved medical policy is outdated or missing?
- What happens if the embedding model or vector database is temporarily unavailable during intake?
- How does the system respond if the provider submits a 1000-page medical record that exceeds LLM context windows?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST ingest PA cases including demographics, clinical notes, diagnosis (ICD-10)/procedure (CPT/HCPCS) codes, benefit rules, PA history, and attachments.
- **FR-002**: System MUST classify cases by request type (imaging, surgery, drug, DME, behavioral health, specialty referral), determine completeness, and flag possible duplicates.
- **FR-003**: System MUST retrieve relevant evidence from medical policy documents, benefit plans, and case attachments, returning citations and confidence scores for every retrieved item.
- **FR-004**: System MUST compare retrieved evidence against policy criteria, labeling each as present, absent, or unclear, and identifying missing documentation.
- **FR-005**: System MUST flag ambiguous or contradictory findings for escalation.
- **FR-006**: System MUST generate human-readable outputs: case summary, evidence table, missing-document request draft (neutral tone), reviewer checklist, and escalation note.
- **FR-007**: System MUST route cases to the appropriate queue (Intake, Nurse Review, Medical Director Review) accompanied by a routing reason and confidence score.
- **FR-008**: System MUST maintain an immutable audit trail per case containing: agent name, input hash, model+version, prompt version, retrieved source IDs, confidence score, output, and timestamp.
- **FR-009**: System MUST provide a reviewer dashboard displaying case status, queue, outputs, and drill-downs into evidence/citations.
- **FR-010**: System MUST strictly operate in "human-in-the-loop" mode and NEVER issue automated medical approval/denial decisions.
- **FR-011**: System MUST support a "synthetic mode" for ingestion to guarantee no real PHI is used in development/testing.
- **FR-012**: System MUST integrate a placeholder/mock OCR interface (abstracting Textract or Azure Form Recognizer) for document parsing.
- **FR-013**: System MUST use pgvector on Postgres for the vector index with a swappable embedding provider interface for the RAG knowledge layer.
- **FR-014**: System MUST utilize the Anthropic API (Claude) via a provider-agnostic interface for agent reasoning.
- **FR-015**: System MUST apply confidence score thresholds: <0.6 auto-flag for manual review, 0.6-0.8 surface with caution indicator, >0.8 present normally.
- **FR-016**: System MUST implement a mocked auth provider for Role-Based Access Control (RBAC) covering the 7 predefined personas, without SSO integration.
- **FR-017**: System MUST enforce an indefinite (append-only) data retention policy for the audit log.

### Key Entities

- **Case**: A PA request container holding metadata (demographics, codes, status, request type).
- **Document**: An attachment or policy file (PDF, text) ingested into the system.
- **EvidenceChunk**: A specific extracted piece of text from a Document used to evaluate criteria.
- **PolicyCriterion**: A specific medical rule or requirement that must be met for the PA.
- **AuditLogEntry**: An immutable record of an agent's action, inputs, sources, and outputs.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of generated clinical/policy statements can be traced back to a cited source document and chunk ID.
- **SC-002**: 100% of processed cases have a complete, queryable audit trail containing all required metadata (agent, model version, timestamp, etc.).
- **SC-003**: 100% of missing documentation is caught by intake completeness checks before the case is routed to a clinical nurse queue.
- **SC-004**: 0% of code paths are capable of emitting a final "approved" or "denied" medical necessity determination.
- **SC-005**: The system successfully processes and routes 95% of single-condition PA requests with under 20 pages of clinical documentation within 2 minutes of document upload.

## Assumptions

- **Mocked Integrations**: Production integration with real payer systems (EMR, claims) is out of scope; all external systems will be mocked.
- **Data Security**: All data in development and CI environments is synthetic. Real PHI is out of scope.
- **User Roles**: The 7 defined personas (Intake, Nurse, MD, Provider Relations, Ops Manager, Auditor, QA) will be managed via a mocked Role-Based Access Control (RBAC) system.
- **Deployment**: The 5 orchestration agents will be independently deployable services.
