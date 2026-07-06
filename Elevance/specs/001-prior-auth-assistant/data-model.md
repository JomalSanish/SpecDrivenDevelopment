# Data Model Specification: Prior Authorization Evidence Assistant

## Entities and Schema

### `Case`
The core aggregate root representing a Prior Authorization request.
- **Fields**:
  - `case_id` (UUID, Primary Key)
  - `member_id` (String, Required)
  - `provider_id` (String, Required)
  - `request_type` (Enum: imaging, surgery, drug, DME, behavioral health, specialty referral)
  - `cpt_hcpcs_codes` (List[String])
  - `icd_10_codes` (List[String])
  - `status` (Enum, State Machine below)
  - `routing_confidence_score` (Float, nullable)
  - `created_at` (Timestamp, UTC)
  - `updated_at` (Timestamp, UTC)

### `Document`
A file or document attached to a specific `Case`.
- **Fields**:
  - `document_id` (UUID, Primary Key)
  - `case_id` (UUID, Foreign Key to Case, Required)
  - `type` (Enum: clinical_note, referral_form, attachment, medical_policy, benefit_plan)
  - `source` (String: e.g. "provider_upload", "policy_kb")
  - `parsed_text` (Text, extracted via OCR/Parser)
  - `embedding_refs` (List[UUID], references to vectors in pgvector)

### `PolicyDocument`
A reference document representing payer medical policy or benefit rules.
- **Fields**:
  - `policy_id` (UUID, Primary Key)
  - `section` (String, e.g. "Coverage Criteria")
  - `text_chunks` (List[Text])
  - `embeddings` (List[Vector], pgvector format)
  - `version` (String, e.g. "2026.Q3")

### `OcrExtractionResult`
The strict JSON contract expected from the mock OCR/Parsing engine (Textract/Azure wrapper).
- **Fields**:
  - `status` (Enum: "success", "failed", "unreadable")
  - `page_count` (Integer)
  - `parsed_text` (Text, full extracted string if success)
  - `error_message` (Text, nullable, populated if status is "failed" or "unreadable")
  - `confidence_score` (Float, 0.0 to 1.0 representing legibility/quality)

### `EvidenceItem`
A discrete piece of evidence extracted by the RAG agent mapping to a Case.
- **Fields**:
  - `evidence_id` (UUID, Primary Key)
  - `case_id` (UUID, Foreign Key to Case, Required)
  - `source` (String, document reference name)
  - `matched_text` (Text, the extracted relevant text)
  - `confidence` (Float, 0.0 to 1.0)
  - `citation_ref` (UUID, Foreign Key to chunk/Document)

### `GapChecklistItem`
The result of the Policy Reasoning agent evaluating an `EvidenceItem` against `PolicyDocument` criteria.
- **Fields**:
  - `checklist_id` (UUID, Primary Key)
  - `case_id` (UUID, Foreign Key to Case, Required)
  - `criterion` (Text, the policy rule being evaluated)
  - `status` (Enum: present, absent, unclear)
  - `rationale` (Text, reasoning provided by agent)
  - `evidence_refs` (List[UUID], Foreign Keys to EvidenceItem). Status "present" strictly requires at least one evidence_ref.

### `CaseSummary`
Structured summary artifacts generated for reviewers.
- **Fields**:
  - `summary_id` (UUID, Primary Key)
  - `case_id` (UUID, Foreign Key to Case, Required)
  - `summary_text` (Text, natural language case summary)
  - `evidence_refs` (List[UUID], references to `EvidenceItem` supporting the summary)

### `RoutingDecision`
The output of the routing logic.
- **Fields**:
  - `routing_id` (UUID, Primary Key)
  - `case_id` (UUID, Foreign Key to Case, Required)
  - `queue` (Enum: Intake, Nurse Review, Medical Director Review)
  - `reason` (Text, natural language explanation)
  - `confidence` (Float, 0.0 to 1.0)

### `AuditLogEntry`
Immutable record for compliance and debugging.
- **Fields**:
  - `audit_id` (UUID, Primary Key)
  - `case_id` (UUID, Foreign Key to Case, Required)
  - `agent` (String, e.g. "Policy Reasoning & Gap Agent")
  - `action` (String)
  - `input_hash` (String, SHA256 of prompt + data)
  - `prompt_version` (String)
  - `model_version` (String, e.g. "claude-3-5-sonnet-20240620")
  - `sources` (List[UUID], references to `EvidenceItem` or `Document`)
  - `timestamp` (Timestamp, UTC)

## State Transitions (`Case.status`)

The `Case` entity follows a strict state machine:

1. **Created**: Initial state when demographics and codes are logged.
2. **Intake Review**: Triggered if completeness checks fail (missing docs detected).
3. **Ready for Evidence Review**: Documents uploaded and parsed; waiting for RAG processing.
4. **Nurse Review**: Default routing after successful evidence extraction and gap analysis mapping.
5. **Medical Director Review**: Escalated state if `RoutingDecision` determines high complexity or ambiguous/contradictory evidence.
6. **Awaiting Provider Documentation**: State entered when Provider Relations drafts a missing-document request.

**Valid Transitions**:
- `Created` → `Ready for Evidence Review`
- `Created` → `Intake Review` (if incomplete)
- `Intake Review` → `Ready for Evidence Review`
- `Ready for Evidence Review` → `Nurse Review`
- `Ready for Evidence Review` → `Medical Director Review` (escalation path)
- `Nurse Review` → `Medical Director Review`
- `Nurse Review` → `Awaiting Provider Documentation`
- `Awaiting Provider Documentation` → `Ready for Evidence Review` (upon receipt of new info)
