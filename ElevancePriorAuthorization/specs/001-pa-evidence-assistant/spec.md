# Feature Specification: pa-evidence-assistant

**Feature Branch**: `001-pa-evidence-assistant`

**Created**: 2026-07-10

**Status**: Draft

**Input**: User description: "Build the Elevance Prior Authorization Evidence Assistant: a payer-side web application..."

## Clarifications

### Session 2026-07-10
- Q: What is the exact confidence-threshold rule for classifying a required document as Present vs. Absent vs. Unclear? → A: Present > 80%, Unclear 50-80%, Absent < 50%
- Q: What happens if a nurse takes no action on a case within SLA — escalation path and ownership? → A: Automatically re-routed to an Escalation/Manager queue
- Q: Whether multiple nurses can be assigned to, or claim, the same case concurrently? → A: Strict locking: Only one nurse can claim/edit a case at a time
- Q: How does a policy document update/version change propagate to cases already in flight against the old version? → A: Locked: In-flight cases use the policy version active at submission time
- Q: What are the required fields for the Accept and Reject actions — does Reject require a structured reason code in addition to free-text notes, and is Accept reversible? → A: Reject requires structured reason code + notes; Accept is irreversible

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Admin Policy Ingestion (Priority: P1)

An admin or compliance user uploads a governing policy document for a specific procedure or service line (e.g., MRI Lumbar Spine). The system parses this document and extracts the definitive list of required supporting documents and evidence types for that policy.

**Why this priority**: Essential to establish the rules against which incoming cases will be evaluated.

**Independent Test**: Can be tested by uploading a sample policy PDF and verifying the extracted list of required evidence matches manual expectations.

**Acceptance Scenarios**:

1. **Given** a PDF policy document, **When** the admin uploads it, **Then** the system extracts a definitive list of required supporting documents (e.g., clinical notes, imaging necessity).
2. **Given** an invalid or unreadable document, **When** uploaded, **Then** the system returns an error asking for a valid document.

---

### User Story 2 - Case Submission & Completeness Check (Priority: P1)

A provider or intake associate uploads case documents (clinical notes, imaging orders) and metadata (member ID, CPT, ICD-10). The system automatically runs a completeness check using local hybrid retrieval to determine if each required policy document is Present, Absent, or Unclear, outputting a checklist with citations and confidence scores.

**Why this priority**: Core value proposition to reduce manual checking time and errors.

**Independent Test**: Can be tested by providing a set of case documents and verifying the generated checklist and citations against a pre-ingested policy.

**Acceptance Scenarios**:

1. **Given** a submitted case missing required documents, **When** the automated check finishes, **Then** it outputs a checklist marking missing items as "Absent".
2. **Given** a case with all required documents, **When** the check finishes, **Then** it marks items as "Present" with accurate citations to the case documents.

---

### User Story 3 - Nurse SLA Escalation (Priority: P2)

A case assigned to the Nurse Review queue breaches its defined SLA threshold for action. The system automatically unassigns it from the original nurse (if claimed) and re-routes it to an Escalation/Manager queue.

**Why this priority**: Prevents cases from stalling and ensures timely decision-making.

**Independent Test**: Can be tested by simulating an SLA breach on a case and verifying it moves to the manager queue.

**Acceptance Scenarios**:

1. **Given** a case in a nurse's queue, **When** the SLA timer expires with no action, **Then** the case is automatically re-routed to the Escalation/Manager queue.

---

### User Story 3 - Nurse Manual Review and Decisioning (Priority: P1)

After the completeness check, the case is routed to Nurse Review. The nurse reviews the summary, uploaded documents, and checklist. The nurse can independently inspect every document, override the system's assessment, and manually record an Accept or Reject decision.

**Why this priority**: Ensures strict adherence to the human-in-the-loop principle and final decision-making capabilities.

**Independent Test**: Can be tested by logging in as a nurse, reviewing a processed case, overriding a checklist item, and submitting a decision.

**Acceptance Scenarios**:

1. **Given** a processed case, **When** the nurse reviews and clicks Accept, **Then** the case state updates to Accepted with timestamp and attribution.
2. **Given** a processed case, **When** the nurse rejects the case, **Then** it is sent back for missing documentation and the state is explicitly updated.

---

### User Story 4 - Audit Logging (Priority: P2)

A Compliance/Audit User views the full audit trail for a case, tracking policy ingestion, completeness check logic (prompts, retrieved chunks, confidence scores), routing steps, and manual nurse decisions.

**Why this priority**: Required for compliance and reconstructability but secondary to the core operational workflow.

**Independent Test**: Can be tested by completing a full case flow and then reviewing the generated audit log for completeness.

**Acceptance Scenarios**:

1. **Given** a completed case, **When** the audit user opens the case logs, **Then** all system prompts, RAG retrievals, and human decisions are visible with timestamps.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST allow admin users to upload and parse policy documents to extract required evidence types.
- **FR-002**: System MUST allow providers/intake users to submit case documents (PDFs, faxes, scans) with case metadata (member ID, provider ID, CPT/HCPCS code, ICD-10 code, service type, requested date).
- **FR-003**: System MUST execute an automated completeness verification checklist comparing case documents against policy requirements.
- **FR-004**: System MUST route all cases to a Nurse Review dashboard after the completeness check.
- **FR-005**: System MUST provide a document viewer in the Nurse Review dashboard alongside the system-generated checklist and citations.
- **FR-006**: System MUST allow the Nurse to override the system's completeness assessment and record a final Accept or Reject decision.
- **FR-007**: System MUST provide draft missing-document communications for provider outreach upon case rejection.
- **FR-008**: System MUST apply explicit confidence thresholds for the automated completeness check: Present (>80%), Unclear (50-80%), Absent (<50%).
- **FR-009**: System MUST enforce strict locking on cases: only one nurse can claim/edit a case concurrently.
- **FR-010**: System MUST lock the policy version: in-flight cases are evaluated against the policy version active at the time of submission, regardless of subsequent updates.
- **FR-011**: System MUST require a structured reason code in addition to free-text notes for the Reject action; the Accept action MUST be irreversible once submitted.
- **FR-012**: System MUST automatically re-route cases to an Escalation/Manager queue if a nurse takes no action within the defined SLA.

### Compliance & Security Requirements (Constitution Mandated)

- **SEC-001**: System MUST NOT use hidden booleans for routing (e.g., `human_review_required`). Must use explicit state fields (`review_status`, `assigned_queue`, `decided_by`, `decision_at`).
- **SEC-002**: System MUST process all PHI and policy documents locally/on-prem. No external/public API calls for RAG, embedding, or inference.
- **SEC-003**: System MUST utilize hybrid retrieval (combining dense semantic and sparse/keyword search like BM25).
- **SEC-004**: System MUST cite specific source documents with stable UUIDs for all evidence claims.
- **SEC-005**: System MUST log all agent actions, prompts, routing, confidence scores, and human decisions for auditability.
- **SEC-006**: System MUST utilize a secrets manager abstraction layer for all credentials.

### Key Entities

- **Policy**: Represents a payer policy document and its extracted required evidence types.
- **Case**: A prior authorization request, containing metadata, uploaded case documents, and explicit state fields (`review_status`, `assigned_queue`, `decided_by`, `decision_at`).
- **Document**: Represents uploaded policy or case documents (PDF, fax, scan) with stable UUIDs.
- **Checklist Item**: Represents a single required evidence piece, its presence status (Present/Absent/Unclear), confidence score, and citation.
- **Audit Log**: A record of every automated agent action and manual human decision.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: System extracts required evidence from policies with a high degree of accuracy, minimizing manual correction.
- **SC-002**: 100% of cases are routed to human review; zero automated Accept/Reject decisions are made.
- **SC-003**: 100% of data processing and RAG inference occurs in the local/on-prem environment without external network egress for document content.
- **SC-004**: Full audit logs are available for 100% of processed cases, capturing all prompts, scores, and decisions.

## Assumptions

- The application will be deployed in a secure on-prem or private VPC environment.
- OCR capabilities are abstracted and run locally.
- Development and testing will use strictly synthetic data (no real PHI).
- User authentication and authorization are handled by an existing enterprise IAM system (e.g., SSO).
