# API Contracts: Cases

**Base path**: `/api/v1/cases`
**Auth required**: Bearer JWT on all endpoints.
**Roles**: intake, nurse, admin (read); intake, admin (create/edit)

---

## GET /api/v1/cases

List cases visible to the caller. Intake sees cases they created. Nurse/Admin see all.

**Auth**: Any authenticated role

**Query params**:
| Param | Type | Description |
|-------|------|-------------|
| `status` | string | Filter by status: `processing`, `pending_review`, `pipeline_error`, `accepted`, `rejected` |
| `service_type` | string | Filter by `requested_service` (partial match) |
| `from_date` | date (ISO) | Filter `created_at >= from_date` |
| `to_date` | date (ISO) | Filter `created_at <= to_date` |
| `page` | int (default 1) | Pagination |
| `page_size` | int (default 25, max 100) | |

**Response 200**:
```json
{
  "items": [
    {
      "id": "<UUID>",
      "member_id": "M123456",
      "requested_service": "MRI Lumbar Spine",
      "provider_name": "Dr. Smith",
      "cpt_hcpcs_code": "72148",
      "icd10_code": "M54.5",
      "requested_date": "2026-07-01",
      "policy_id": "<UUID>",
      "policy_name": "Lumbar Spine MRI — 2026",
      "status": "pending_review",
      "is_escalated": false,
      "claimed_by_name": null,
      "decided_by_name": null,
      "decision": null,
      "admin_edit_comment": null,
      "created_at": "2026-07-20T08:00:00Z"
    }
  ],
  "total": 42,
  "page": 1,
  "page_size": 25
}
```

---

## POST /api/v1/cases/upload-documents

Upload documents before creating a case. Returns extracted field suggestions.

**Auth**: intake, admin

**Request**: `multipart/form-data`
- `files`: one or more PDF files

**Response 200**:
```json
{
  "upload_session_id": "<UUID>",
  "document_ids": ["<UUID>", "<UUID>"],
  "extracted_fields": {
    "member_id":          { "value": "M123456", "ai_extracted": true },
    "provider_name":      { "value": null,       "ai_extracted": false },
    "cpt_hcpcs_code":     { "value": "72148",    "ai_extracted": true },
    "icd10_code":         { "value": null,        "ai_extracted": false },
    "requested_service":  { "value": "MRI Lumbar Spine", "ai_extracted": true },
    "requested_date":     { "value": "2026-07-01", "ai_extracted": true }
  }
}
```

Fields with `ai_extracted: false` were not confidently found — left null (FR-013). Fields with `ai_extracted: true` should be shown pre-filled and labeled "AI-extracted — please verify."

---

## POST /api/v1/cases

Create a case from an upload session. Triggers background completeness pipeline.

**Auth**: intake, admin

**Request** (`application/json`):
```json
{
  "upload_session_id": "<UUID>",
  "member_id": "M123456",
  "requested_service": "MRI Lumbar Spine",
  "provider_name": "Dr. Smith",
  "cpt_hcpcs_code": "72148",
  "icd10_code": null,
  "requested_date": "2026-07-01",
  "policy_id": "<UUID>"
}
```

**Validation**: `member_id` and `requested_service` MUST be non-empty (FR-013a). Returns 422 if absent.

**Response 202** (pipeline starts asynchronously):
```json
{
  "id": "<UUID>",
  "status": "processing",
  "message": "Case created. Evidence analysis is running in the background."
}
```

---

## GET /api/v1/cases/{case_id}

Get full case detail including completeness report (once pipeline complete).

**Auth**: Any authenticated role

**Response 200**:
```json
{
  "id": "<UUID>",
  "member_id": "M123456",
  "requested_service": "MRI Lumbar Spine",
  "provider_name": "Dr. Smith",
  "cpt_hcpcs_code": "72148",
  "icd10_code": null,
  "requested_date": "2026-07-01",
  "policy_id": "<UUID>",
  "policy_name": "Lumbar Spine MRI — 2026",
  "status": "pending_review",
  "is_escalated": false,
  "claimed_by_id": null,
  "claimed_by_name": null,
  "lock_last_active_at": null,
  "decided_by_name": null,
  "decision": null,
  "admin_edit_comment": null,
  "admin_edit_by_name": null,
  "admin_edit_at": null,
  "documents": [
    { "id": "<UUID>", "original_filename": "clinical_note.pdf", "page_count": 4 }
  ],
  "completeness_report": [
    {
      "requirement_id": "<UUID>",
      "requirement_description": "6 weeks of conservative therapy documented",
      "requirement_type": "narrative",
      "verdict": "absent",
      "supporting_chunks": [],
      "keyword_miss": false
    },
    {
      "requirement_id": "<UUID>",
      "requirement_description": "Neurological symptoms present",
      "requirement_type": "narrative",
      "verdict": "present",
      "supporting_chunks": [
        {
          "chunk_id": "<UUID>",
          "page_number": 2,
          "excerpt": "Patient reports radiating pain and numbness...",
          "extraction_method": "native"
        }
      ],
      "keyword_miss": false
    }
  ],
  "case_summary": "Member M123456 requested MRI Lumbar Spine. Clinical note documents neurological symptoms but conservative therapy records are absent.",
  "created_at": "2026-07-20T08:00:00Z"
}
```

**Response 404**: Case not found.

---

## GET /api/v1/cases/{case_id}/status

Lightweight status poll endpoint for frontend polling (FR-018).

**Auth**: Any authenticated role

**Response 200**:
```json
{
  "id": "<UUID>",
  "status": "processing",
  "is_escalated": false
}
```

---

## GET /api/v1/policies (for dropdown)

Returns all policies for the case creation dropdown. Sorted by name.

**Auth**: Any authenticated role

**Response 200**:
```json
{
  "items": [
    { "id": "<UUID>", "name": "Cardiac Imaging — 2026" },
    { "id": "<UUID>", "name": "Lumbar Spine MRI — 2026" }
  ]
}
```
