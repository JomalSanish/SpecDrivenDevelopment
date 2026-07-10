# Data Model

## Core Entities

### Policy
- `id`: UUID (Primary Key)
- `title`: String
- `service_line_code`: String
- `version`: String
- `active`: Boolean
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
- `review_status`: Enum (`pending_verification`, `in_nurse_review`, `accepted`, `rejected`, `returned_to_provider`)
- `assigned_queue`: String
- `claimed_by_id`: UUID (Nullable, Strict lock)
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
- `status`: Enum (`Present`, `Absent`, `Unclear`)
- `confidence_score`: Float
- `matched_document_id`: UUID (Nullable)
- `matched_chunk_id`: UUID (Nullable)
- `reasoning_log`: Text

### AuditLog
- `id`: UUID (Primary Key)
- `case_id`: UUID (Foreign Key)
- `actor_id`: String (System Agent or Human UUID)
- `action_type`: String
- `details`: JSON (e.g., prompts used, routing decision made, LLM version)
- `timestamp`: Timestamp
