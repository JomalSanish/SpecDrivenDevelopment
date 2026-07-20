# API Contracts: Policy Management

**Base path**: `/api/v1/policies`
**Auth required**: Bearer JWT on all endpoints.
**Roles**: intake, nurse (read only); admin (all operations)

---

## GET /api/v1/policies

List all policies. Available to all roles.

**Auth**: Any authenticated role

**Response 200**:
```json
{
  "items": [
    {
      "id": "<UUID>",
      "name": "Lumbar Spine MRI — 2026",
      "sla_hours": 48,
      "requirement_count": 5,
      "created_by_name": "Admin User",
      "updated_at": "2026-07-20T09:00:00Z"
    }
  ],
  "total": 3
}
```

---

## GET /api/v1/policies/{policy_id}

Get policy detail with full requirement checklist.

**Auth**: Any authenticated role

**Response 200**:
```json
{
  "id": "<UUID>",
  "name": "Lumbar Spine MRI — 2026",
  "sla_hours": 48,
  "requirements": [
    {
      "id": "<UUID>",
      "description": "6 weeks of conservative therapy documented",
      "requirement_type": "narrative",
      "matching_criteria": null,
      "display_order": 0
    },
    {
      "id": "<UUID>",
      "description": "CPT code 72148 included in request",
      "requirement_type": "identifier",
      "matching_criteria": { "code": "72148" },
      "display_order": 1
    }
  ],
  "created_by_name": "Admin User",
  "updated_at": "2026-07-20T09:00:00Z"
}
```

---

## POST /api/v1/policies/upload

Upload a policy PDF + name. Triggers extraction pipeline.
If a policy with the same `name` already exists, it is overwritten (FR-044).

**Auth**: admin only — returns 403 for other roles

**Request**: `multipart/form-data`
- `file`: PDF file
- `name`: string (required, human-readable policy name)
- `sla_hours`: integer (optional, default 48)

**Response 202**:
```json
{
  "policy_id": "<UUID>",
  "name": "Lumbar Spine MRI — 2026",
  "status": "extracting",
  "message": "Policy uploaded. Requirement extraction is in progress."
}
```

---

## GET /api/v1/policies/{policy_id}/draft-requirements

Get the AI-extracted draft requirements for admin review before saving (FR-043).
Available immediately after upload completes extraction.

**Auth**: admin only

**Response 200**:
```json
{
  "policy_id": "<UUID>",
  "name": "Lumbar Spine MRI — 2026",
  "extraction_status": "complete",
  "draft_requirements": [
    {
      "temp_id": "draft-001",
      "description": "6 weeks of conservative therapy documented",
      "requirement_type": "narrative",
      "matching_criteria": null,
      "display_order": 0
    }
  ]
}
```

`extraction_status`: `"extracting"` | `"complete"` | `"error"`

---

## POST /api/v1/policies/{policy_id}/requirements

Save the finalized requirement checklist (admin's edits applied). Overwrites any existing requirements for this policy.

**Auth**: admin only

**Request** (`application/json`):
```json
{
  "requirements": [
    {
      "description": "6 weeks of conservative therapy documented",
      "requirement_type": "narrative",
      "matching_criteria": null,
      "display_order": 0
    },
    {
      "description": "Neurological symptoms present",
      "requirement_type": "narrative",
      "matching_criteria": null,
      "display_order": 1
    },
    {
      "description": "CPT code 72148 included",
      "requirement_type": "identifier",
      "matching_criteria": { "code": "72148" },
      "display_order": 2
    }
  ]
}
```

**Response 200**:
```json
{
  "policy_id": "<UUID>",
  "saved_requirements": 3
}
```

---

## DELETE /api/v1/policies/{policy_id}

Delete a policy. Cases already referencing it retain their evidence snapshot.

**Auth**: admin only

**Response 204**: No content.
