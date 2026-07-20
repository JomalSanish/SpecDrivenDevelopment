# API Contracts: Admin

**Base path**: `/api/v1/admin`
**Auth required**: Bearer JWT — **admin role only** on all endpoints. Returns 403 for any other role.

---

## GET /api/v1/admin/cases

Full case table for admin — all cases regardless of status (FR-050/FR-051).

**Query params**:
| Param | Type | Description |
|-------|------|-------------|
| `status` | string | Filter by status |
| `is_escalated` | bool | Filter overdue cases |
| `policy_id` | UUID | Filter by policy |
| `from_date` | date | Filter `created_at >=` |
| `to_date` | date | Filter `created_at <=` |
| `search` | string | Partial match on member_id, requested_service |
| `page` | int | Default 1 |
| `page_size` | int | Default 25, max 100 |

**Response 200**:
```json
{
  "items": [
    {
      "id": "<UUID>",
      "member_id": "M123456",
      "requested_service": "MRI Lumbar Spine",
      "policy_name": "Lumbar Spine MRI — 2026",
      "status": "accepted",
      "is_escalated": false,
      "claimed_by_name": null,
      "decided_by_name": "Jane Nurse",
      "decision": "accepted",
      "admin_edit_comment": null,
      "created_at": "2026-07-20T08:00:00Z"
    }
  ],
  "total": 100,
  "page": 1,
  "page_size": 25
}
```

---

## PATCH /api/v1/admin/cases/{case_id}

Edit any case field. If the case has a decision (`accepted`/`rejected`), `admin_comment` is required and the system re-queues the case for nurse review (FR-052/FR-053/FR-054).

**Request** (`application/json`):
```json
{
  "member_id": "M123456",
  "requested_service": "MRI Lumbar Spine — Revised",
  "provider_name": "Dr. Johnson",
  "cpt_hcpcs_code": "72148",
  "icd10_code": "M54.5",
  "requested_date": "2026-07-02",
  "policy_id": "<UUID>",
  "admin_comment": "Corrected ICD-10 code per provider clarification."
}
```

All fields are optional in the patch body — only provided fields are updated.
`admin_comment` is **required** if the case status is `accepted` or `rejected`. Returns 422 if absent.

**Response 200**:
```json
{
  "id": "<UUID>",
  "status": "pending_review",
  "admin_edit_comment": "Corrected ICD-10 code per provider clarification.",
  "admin_edit_by": "Admin User",
  "admin_edit_at": "2026-07-20T14:00:00Z",
  "requeued": true
}
```

`requeued: true` only when a decided case was moved back to `pending_review`.

---

## POST /api/v1/admin/cases/{case_id}/rerun-pipeline

Re-trigger the completeness pipeline for a case in `pipeline_error` status.

**Response 202**:
```json
{ "case_id": "<UUID>", "status": "processing" }
```

**Response 400**: `{ "detail": "Case is not in pipeline_error status" }`

---

## GET /api/v1/admin/cases/{case_id}/history

Returns the status transition history for a case (from `case_status_history`).

**Response 200**:
```json
{
  "case_id": "<UUID>",
  "history": [
    {
      "from_status": "processing",
      "to_status": "pending_review",
      "actor_name": "System",
      "actor_role": "system",
      "decision": null,
      "comment": null,
      "transitioned_at": "2026-07-20T08:05:00Z"
    },
    {
      "from_status": "pending_review",
      "to_status": "accepted",
      "actor_name": "Jane Nurse",
      "actor_role": "nurse",
      "decision": "accepted",
      "comment": null,
      "transitioned_at": "2026-07-20T10:30:00Z"
    },
    {
      "from_status": "accepted",
      "to_status": "pending_review",
      "actor_name": "Admin User",
      "actor_role": "admin",
      "decision": null,
      "comment": "Corrected ICD-10 code per provider clarification.",
      "transitioned_at": "2026-07-20T14:00:00Z"
    }
  ]
}
```

---

## GET /api/v1/admin/users

List all staff accounts.

**Response 200**:
```json
{
  "items": [
    {
      "id": "<UUID>",
      "username": "jnurse",
      "full_name": "Jane Nurse",
      "role": "nurse",
      "is_active": true,
      "created_at": "2026-07-01T09:00:00Z"
    }
  ],
  "total": 12
}
```

---

## POST /api/v1/admin/users

Create a new staff account.

**Request** (`application/json`):
```json
{
  "username": "jnurse2",
  "full_name": "Bob Nurse",
  "password": "initial_password",
  "role": "nurse"
}
```

**Response 201**:
```json
{
  "id": "<UUID>",
  "username": "jnurse2",
  "full_name": "Bob Nurse",
  "role": "nurse",
  "is_active": true
}
```

**Response 409**: `{ "detail": "Username already exists" }`

---

## PATCH /api/v1/admin/users/{user_id}

Update user: deactivate, reactivate, or reset password.

**Request** (`application/json`):
```json
{
  "is_active": false,
  "new_password": "reset_password"
}
```

All fields optional. At least one must be provided.

**Response 200**: Updated user object (same shape as list item).

---

## GET /api/v1/admin/audit-log

Search the immutable audit log (FR-057).

**Query params**:
| Param | Type | Description |
|-------|------|-------------|
| `case_id` | UUID | Filter by case |
| `actor_id` | UUID | Filter by user |
| `event_type` | string | Filter by event type |
| `from_date` | datetime | Filter `created_at >=` |
| `to_date` | datetime | Filter `created_at <=` |
| `page` | int | Default 1 |
| `page_size` | int | Default 50, max 200 |

**Response 200**:
```json
{
  "items": [
    {
      "id": "<UUID>",
      "event_type": "nurse_decision",
      "actor_name": "Jane Nurse",
      "actor_role": "nurse",
      "case_id": "<UUID>",
      "payload": {
        "decision": "accepted",
        "notes": "Documentation complete."
      },
      "created_at": "2026-07-20T10:30:00Z"
    }
  ],
  "total": 247,
  "page": 1,
  "page_size": 50
}
```

> **Note**: No DELETE or PATCH endpoint exists for audit_logs. Any attempt via direct DB connection is also prohibited by application design (FR-058).
