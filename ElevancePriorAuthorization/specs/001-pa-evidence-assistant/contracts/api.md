# API Contracts

## Admin Routes
- `POST /api/v1/admin/policies`
  - Upload a PDF policy document.
  - Triggers extraction of PolicyRequirement items.
  - Returns: `{ "policy_id": "uuid", "requirements": [...] }`

## Intake Routes
- `POST /api/v1/intake/cases`
  - Submit case metadata and documents.
  - Payload: `{ "member_id": "...", "cpt_code": "...", "documents": [file_uploads] }`
  - Returns: `{ "case_id": "uuid", "status": "pending_verification" }`

## Nurse Review Routes
- `GET /api/v1/review/cases`
  - List cases `in_nurse_review`.
- `GET /api/v1/review/cases/{case_id}`
  - Fetch case details, documents, and `CompletenessReport`.
- `POST /api/v1/review/cases/{case_id}/claim`
  - Strict lock endpoint. Returns 409 if already claimed.
- `POST /api/v1/review/cases/{case_id}/decision`
  - Payload: `{ "action": "Accept|Reject", "reason_code": "...", "notes": "..." }`
  - Returns: `{ "status": "success", "new_state": "accepted|rejected" }`
