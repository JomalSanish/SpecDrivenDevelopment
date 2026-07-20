# API Contracts: Nurse Review

**Base path**: `/api/v1/nurse-review`
**Auth required**: Bearer JWT — nurse or admin role on all endpoints.

---

## GET /api/v1/nurse-review/queue

Returns the nurse review queue: unclaimed cases + cases claimed by this nurse.
Escalated cases sorted first, then oldest `entered_review_at` (FR-027).

**Auth**: nurse, admin

**Query params**: `page`, `page_size` (default 25)

**Response 200**:
```json
{
  "items": [
    {
      "id": "<UUID>",
      "member_id": "M123456",
      "requested_service": "MRI Lumbar Spine",
      "policy_name": "Lumbar Spine MRI — 2026",
      "status": "pending_review",
      "is_escalated": true,
      "claimed_by_name": null,
      "claimed_by_me": false,
      "admin_edit_comment": null,
      "entered_review_at": "2026-07-18T10:00:00Z"
    }
  ],
  "total": 8,
  "page": 1,
  "page_size": 25
}
```

`claimed_by_name` is non-null when locked by another nurse (shown as "Locked by [name]"). `claimed_by_me` is `true` when the calling nurse holds the lock.

---

## POST /api/v1/nurse-review/cases/{case_id}/lock

Acquire exclusive lock on a case. Atomic conditional UPDATE — only succeeds if `claimed_by_id IS NULL` (or the lock has expired).

**Auth**: nurse, admin

**Response 200**:
```json
{
  "locked": true,
  "locked_by": "Jane Nurse",
  "lock_expires_at": "2026-07-20T14:00:00Z"
}
```

**Response 409** (already locked by another nurse whose lock has not expired):
```json
{
  "detail": "Case is locked by Jane Nurse",
  "locked_by": "Jane Nurse",
  "lock_expires_at": "2026-07-20T13:30:00Z"
}
```

---

## POST /api/v1/nurse-review/cases/{case_id}/heartbeat

Refresh `lock_last_active_at` to extend the 30-minute inactivity window. Frontend sends every 120 seconds (FR-032).

**Auth**: nurse, admin (must be the current lock holder)

**Response 200**:
```json
{ "lock_last_active_at": "2026-07-20T13:02:00Z" }
```

**Response 403**: `{ "detail": "You do not hold the lock on this case" }`

---

## DELETE /api/v1/nurse-review/cases/{case_id}/lock

Explicitly release the lock (nurse navigates away via Release button).

**Auth**: nurse, admin (must be the current lock holder)

**Response 204**: No content.

---

## POST /api/v1/nurse-review/cases/{case_id}/decision

Record nurse accept or reject decision. Clears the lock.

**Auth**: nurse, admin (must be the current lock holder)

**Request** (`application/json`):
```json
{
  "decision": "accepted",
  "notes": "Documentation is complete. Conservative therapy records present."
}
```

`decision` MUST be `"accepted"` or `"rejected"`. `notes` is optional free text.

**Response 200**:
```json
{
  "case_id": "<UUID>",
  "decision": "accepted",
  "decided_by": "Jane Nurse",
  "decided_at": "2026-07-20T13:10:00Z"
}
```

**Response 403**: Caller does not hold the lock.
**Response 422**: Invalid decision value.

---

## GET /api/v1/nurse-review/decided

Cases the calling nurse has previously decided, in tabs: accepted and rejected.

**Auth**: nurse, admin

**Query params**: `decision` (`accepted` | `rejected`), `page`, `page_size`

**Response 200**: Same shape as queue response, filtered to decided cases.

---

## GET /api/v1/documents/{document_id}/stream

Stream a PDF for the Document Viewer. Returns raw PDF bytes.

**Auth**: nurse, admin (intake may also access documents for cases they created)

**Response 200**: `Content-Type: application/pdf` — binary PDF stream.
**Response 404**: Document not found.
