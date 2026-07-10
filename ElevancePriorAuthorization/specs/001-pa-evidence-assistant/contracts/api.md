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
  - `action: "Reject"` maps internally to `review_status: "returned_to_provider"` — there is no separate `rejected` state; Reject always means the case goes back to the provider for more documentation.
  - Returns: `{ "status": "success", "new_state": "accepted|returned_to_provider" }`
- `POST /api/v1/review/cases/{case_id}/checklist/{item_id}/override`
  - Nurse manually overrides a system-generated `CompletenessReportItem` status.
  - Payload: `{ "overridden_status": "Present|Absent|Unclear" }`
  - Sets `overridden_status`, `overridden_by_id`, `overridden_at` on the item; leaves the original `status` untouched. Writes an `AuditLog` row with `action_type: "checklist_override"`.
  - Returns: `{ "status": "success", "item_id": "uuid", "overridden_status": "..." }`

## Operations & Audit Routes
- `GET /api/v1/ops/queues`
  - Returns queue statistics for the Operations Dashboard: counts of Unassigned, Claimed, SLA Breached, Escalated cases.
- `GET /api/v1/ops/cases?member_id=...&cpt_code=...`
  - Search/filter cases by member ID and/or CPT code.
- `GET /api/v1/audit/cases/{case_id}`
  - Full read-only `AuditLog` trail for a case: timestamps, actor identities, prompts, retrieved chunk IDs, confidence scores, and decisions — powers the Operations Dashboard's audit view and User Story 4.
