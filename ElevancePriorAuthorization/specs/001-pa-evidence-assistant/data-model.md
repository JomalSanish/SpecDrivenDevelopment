# Data Model

## Core Entities

### Policy
- `id`: UUID (Primary Key)
- `title`: String
- `service_line_code`: String
- `version`: String
- `active`: Boolean
- `sla_hours`: Integer (Nullable — nurse review SLA duration for cases against this policy; falls back to a system-wide default when unset)
- `created_at`: Timestamp

### PolicyRequirement
- `id`: UUID (Primary Key)
- `policy_id`: UUID (Foreign Key)
- `description`: String (e.g., "Clinical notes from last 6 months")
- `matching_criteria`: JSON/Text (Instructions for RAG reasoning)

### Case
- `id`: UUID (Primary Key)
- `member_id`: String
- `provider_id`: String
- `cpt_code`: String
- `icd10_code`: String
- `service_type`: String
- `requested_date`: Timestamp
- `policy_id`: UUID (Foreign Key - locked at submission)
- `review_status`: Enum (`pending_verification`, `in_nurse_review`, `accepted`, `returned_to_provider`) — no separate `rejected` value: a nurse's "Reject" action always means the case is sent back to the provider for more documentation, so it maps to `returned_to_provider`, never a terminal denial state
- `assigned_queue`: Enum (`nurse_review`, `escalation_manager`, `medical_director_review`)
- `claimed_by_id`: UUID (Nullable, Strict lock)
- `entered_review_at`: Timestamp (Nullable — set when `review_status` first becomes `in_nurse_review`; SLA escalation is measured from this timestamp, not from `claimed_by_id`, so an unclaimed case can still breach SLA and escalate)
- `decided_by_id`: UUID (Nullable)
- `decision_reason`: String (Structured code + notes)
- `decision_at`: Timestamp

### Document (Case Document)
- `id`: UUID (Primary Key)
- `case_id`: UUID (Foreign Key)
- `document_type`: Enum (PDF, Scan, Fax)
- `storage_path`: String (MinIO object key)
- `uploaded_at`: Timestamp

### CompletenessReportItem
- `id`: UUID (Primary Key)
- `case_id`: UUID (Foreign Key)
- `policy_requirement_id`: UUID (Foreign Key)
- `status`: Enum (`Present`, `Absent`, `Unclear`) — the system-generated (original) status
- `confidence_score`: Float
- `matched_document_id`: UUID (Nullable)
- `matched_chunk_id`: UUID (Nullable)
- `reasoning_log`: Text
- `overridden_status`: Enum (`Present`, `Absent`, `Unclear`, Nullable) — set only when a nurse manually overrides the system assessment; `status` is left untouched so the original agent output remains reconstructable (resolves CHK009)
- `overridden_by_id`: UUID (Nullable) — nurse who performed the override
- `overridden_at`: Timestamp (Nullable)

### AuditLog
- `id`: UUID (Primary Key)
- `case_id`: UUID (Foreign Key)
- `actor_id`: String (System Agent or Human UUID)
- `action_type`: Enum (`policy_ingested`, `case_submitted`, `rag_retrieval`, `llm_completion`, `checklist_override`, `case_claimed`, `case_decision`, `sla_escalation`) — constrained rather than free-text so override events (CHK009) and every other traced action are queryable and reportable, not just present as arbitrary strings
- `details`: JSON (e.g., prompts used, routing decision made, LLM version; for `checklist_override` this MUST include `completeness_report_item_id`, `original_status`, and `new_status`)
- `timestamp`: Timestamp
