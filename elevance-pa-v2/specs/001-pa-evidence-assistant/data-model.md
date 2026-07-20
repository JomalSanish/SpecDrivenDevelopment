# Data Model: Elevance PA Evidence Assistant (v2)

**Feature**: `001-pa-evidence-assistant`
**Date**: 2026-07-20
**Source**: `specs/001-pa-evidence-assistant/spec.md` — Key Entities section + clarifications

All tables managed by Alembic migrations. PostgreSQL 16. No applied migration may be edited (Constitution Principle XIV).

---

## Entity Diagram

```
users ──────────────────────────────────────────────────────┐
  │ 1:N refresh_tokens                                       │
  │ 1:N cases (intake_by)                                    │
  │ 1:N cases (claimed_by)                                   │
  │ 1:N cases (decided_by)                                   │
  │ 1:N cases (admin_edit_by)                                │
  │ 1:N audit_logs (actor)                                   │
  └──────────────────────────────────────────────────────────┘

policies ──────────────────── 1:N ──── policy_requirements
  │ 1:N cases (policy_id)
  └─────────────────────────────────────────────────────────

cases ──── 1:N ──── documents ──── 1:N ──── [Qdrant chunks]
  │  1:N case_status_history
  │  1:N completeness_report_items ──── N:1 ──── policy_requirements
  │  1:N audit_logs (case_id)
  └─────────────────────────────────────────────────────────
```

---

## Tables

### `users`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK, default gen_random_uuid() | |
| `username` | VARCHAR(100) | UNIQUE, NOT NULL | Login identifier |
| `full_name` | VARCHAR(200) | NOT NULL | Displayed in lock labels, audit log |
| `hashed_password` | TEXT | NOT NULL | argon2 hash |
| `role` | ENUM('intake','nurse','admin') | NOT NULL | |
| `is_active` | BOOLEAN | NOT NULL, default TRUE | Deactivated users cannot authenticate |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now() | |
| `created_by_id` | UUID | FK → users(id), nullable | NULL for seed/first admin |

**Indexes**: `username` (unique), `role`

---

### `refresh_tokens`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK | |
| `user_id` | UUID | FK → users(id), NOT NULL | |
| `token_hash` | TEXT | NOT NULL | argon2(raw_token) |
| `expires_at` | TIMESTAMPTZ | NOT NULL | now() + 7 days |
| `revoked` | BOOLEAN | NOT NULL, default FALSE | Set TRUE on logout or rotation |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now() | |

**Indexes**: `user_id`, `revoked`, `expires_at`

---

### `policies`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK | |
| `name` | VARCHAR(300) | UNIQUE, NOT NULL | Human-readable; shown in dropdown |
| `file_path` | TEXT | NOT NULL | Path in StorageService |
| `sla_hours` | INTEGER | NOT NULL, default 48 | SLA threshold for escalation |
| `created_by_id` | UUID | FK → users(id), NOT NULL | Must be admin |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, default now() | |

**Indexes**: `name` (unique, case-insensitive), `created_at`

**Notes**: Re-uploading with an existing name performs an UPDATE (overwrite) — no version history in this table (Constitution Principle IX).

---

### `policy_requirements`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK | |
| `policy_id` | UUID | FK → policies(id), ON DELETE CASCADE | |
| `description` | TEXT | NOT NULL | Plain-English requirement text |
| `requirement_type` | ENUM('identifier','narrative','mixed') | NOT NULL | Drives retrieval routing |
| `matching_criteria` | JSONB | nullable | Keywords, time windows for identifier/mixed types |
| `display_order` | INTEGER | NOT NULL, default 0 | Admin-specified sort order |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now() | |

**Indexes**: `policy_id`, `requirement_type`

---

### `cases`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK | |
| `member_id` | VARCHAR(100) | NOT NULL | Required field (FR-013a) |
| `requested_service` | TEXT | NOT NULL | Required field (FR-013a) |
| `provider_name` | VARCHAR(300) | nullable | Optional at submission |
| `cpt_hcpcs_code` | VARCHAR(20) | nullable | Optional at submission |
| `icd10_code` | VARCHAR(20) | nullable | Optional at submission |
| `requested_date` | DATE | nullable | Optional at submission |
| `policy_id` | UUID | FK → policies(id), NOT NULL | Selected at submission; snapshot via case_status_history |
| `intake_by_id` | UUID | FK → users(id), NOT NULL | |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now() | |
| `status` | ENUM('processing','pending_review','pipeline_error','accepted','rejected') | NOT NULL, default 'processing' | |
| `entered_review_at` | TIMESTAMPTZ | nullable | Set when status → pending_review; used for SLA |
| `is_escalated` | BOOLEAN | NOT NULL, default FALSE | Set by SLA service |
| `claimed_by_id` | UUID | FK → users(id), nullable | Currently locking nurse |
| `claimed_at` | TIMESTAMPTZ | nullable | |
| `lock_last_active_at` | TIMESTAMPTZ | nullable | Updated by heartbeat; used for 30-min expiry |
| `decided_by_id` | UUID | FK → users(id), nullable | Nurse who last made a decision |
| `decided_at` | TIMESTAMPTZ | nullable | |
| `decision` | ENUM('accepted','rejected') | nullable | Latest nurse decision |
| `admin_edit_by_id` | UUID | FK → users(id), nullable | Set when admin triggers re-review |
| `admin_edit_at` | TIMESTAMPTZ | nullable | |
| `admin_edit_comment` | TEXT | nullable | Mandatory comment on admin edit of decided case |

**Indexes**: `status`, `is_escalated`, `claimed_by_id`, `policy_id`, `created_at`, `entered_review_at`

**Business rules**:
- `status` transitions: `processing` → `pending_review` (pipeline success) | `pipeline_error` (pipeline fail)
- `pending_review` → `accepted` | `rejected` (nurse decision)
- `accepted`|`rejected` → `pending_review` (admin edit with comment — also writes case_status_history row)
- `admin_edit_comment` MUST NOT be NULL when admin transitions a decided case back to `pending_review`

---

### `case_status_history`

Append-only. Never updated or deleted. Records every status transition to preserve original decisions.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK | |
| `case_id` | UUID | FK → cases(id), NOT NULL | |
| `from_status` | VARCHAR(50) | NOT NULL | Status before the transition |
| `to_status` | VARCHAR(50) | NOT NULL | Status after the transition |
| `actor_id` | UUID | FK → users(id), NOT NULL | Who caused the transition |
| `actor_role` | VARCHAR(20) | NOT NULL | Role snapshot at time of transition |
| `decision` | ENUM('accepted','rejected') | nullable | Nurse decision if applicable |
| `comment` | TEXT | nullable | Admin edit comment if applicable |
| `transitioned_at` | TIMESTAMPTZ | NOT NULL, default now() | |

**Indexes**: `case_id`, `transitioned_at`

---

### `documents`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK | |
| `case_id` | UUID | FK → cases(id), ON DELETE CASCADE | |
| `original_filename` | VARCHAR(500) | NOT NULL | |
| `file_path` | TEXT | NOT NULL | StorageService path |
| `page_count` | INTEGER | nullable | Set after extraction |
| `uploaded_by_id` | UUID | FK → users(id), NOT NULL | |
| `uploaded_at` | TIMESTAMPTZ | NOT NULL, default now() | |

**Indexes**: `case_id`

**Note**: Chunk data (text, embeddings) lives in Qdrant — not in PostgreSQL. Only document metadata lives here.

---

### `completeness_report_items`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK | |
| `case_id` | UUID | FK → cases(id), ON DELETE CASCADE | |
| `requirement_id` | UUID | FK → policy_requirements(id) | |
| `verdict` | ENUM('present','absent','unclear') | NOT NULL | Derived from confidence_score |
| `confidence_score` | FLOAT | NOT NULL | Raw 0.0–1.0 from reasoning agent; never shown in UI |
| `supporting_chunks` | JSONB | NOT NULL | Array of {chunk_id, page_number, excerpt, extraction_method} |
| `reasoning_log` | TEXT | NOT NULL | LLM chain-of-thought; stored for audit |
| `keyword_miss` | BOOLEAN | NOT NULL, default FALSE | True if keyword-miss cap was applied |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now() | |

**Indexes**: `case_id`, `requirement_id`, `verdict`

**Verdict mapping** (Constitution Principle VII):
- `confidence_score >= 0.85` → `present`
- `confidence_score < 0.70` → `absent`
- `0.70 <= confidence_score < 0.85` → `unclear`
- `keyword_miss = TRUE` on identifier-bearing requirement → verdict capped at `unclear` regardless of score

---

### `audit_logs`

Immutable — no UPDATE or DELETE ever issued against this table. No API endpoint permits modification.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK | |
| `event_type` | VARCHAR(100) | NOT NULL | See Event Types below |
| `actor_id` | UUID | FK → users(id), nullable | NULL for system events (pipeline, SLA) |
| `actor_role` | VARCHAR(20) | nullable | Role snapshot |
| `case_id` | UUID | FK → cases(id), nullable | NULL for user management events |
| `payload` | JSONB | NOT NULL | Before/after snapshot or AI call metadata |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now() | |

**Indexes**: `event_type`, `actor_id`, `case_id`, `created_at`

**Event types**:
| Event Type | Triggered By |
|---|---|
| `case_created` | Intake associate submits new case |
| `document_uploaded` | Document upload |
| `pipeline_started` | Background pipeline begins |
| `pipeline_completed` | All requirements evaluated |
| `pipeline_error` | Pipeline fails after retries |
| `ai_call` | Each LLM call (model, prompt hash, response, confidence, latency) |
| `nurse_lock_acquired` | Nurse opens case |
| `nurse_lock_heartbeat` | Heartbeat refreshes lock (sampled — not every ping) |
| `nurse_lock_released` | Manual release by nurse |
| `nurse_lock_expired` | Auto-release by background job |
| `nurse_decision` | Accept or Reject |
| `admin_case_edit` | Admin edits any case field |
| `admin_case_requeued` | Admin edit triggers re-review of decided case |
| `sla_escalation` | SLA service flags case is_escalated = TRUE |
| `policy_created` | Admin creates/overwrites policy |
| `policy_requirement_saved` | Admin finalizes requirement checklist |
| `user_created` | Admin creates user account |
| `user_deactivated` | Admin deactivates account |
| `user_login` | Successful authentication |
| `user_logout` | Explicit logout / refresh token revocation |
| `user_login_failed` | Failed authentication attempt |

---

## Qdrant Data Model

**Collection**: `pa-evidence`

**Named vectors**:
- `dense`: dim=768, distance=Cosine (nomic-embed-text output)
- `sparse`: Qdrant native sparse vector (BM25 statistical model)

**Point payload**:
```json
{
  "case_id": "<UUID>",
  "document_id": "<UUID>",
  "chunk_id": "<UUID>",
  "page_number": 1,
  "chunk_index": 0,
  "text": "...",
  "extraction_method": "native"
}
```

**Filter pattern** (always applied per search):
```json
{ "must": [{ "key": "case_id", "match": { "value": "<case_id>" } }] }
```

---

## State Machine: Case Status

```
[CREATED]
    │
    ▼
processing ──(pipeline success)──► pending_review ──(nurse accept)──► accepted
    │                                   │                                  │
    │(pipeline fail)                    │(nurse reject)                    │(admin edit
    ▼                                   ▼                                  │  + comment)
pipeline_error                       rejected ─────────────────────────────┘
                                         │
                                         │(admin edit + comment)
                                         ▼
                                    pending_review  [tagged "Admin Edit"]
```

All transitions write to `case_status_history` and `audit_logs`.

---

## Validation Rules (from spec FRs)

| Rule | Source |
|---|---|
| `cases.member_id` NOT NULL on submit | FR-013a |
| `cases.requested_service` NOT NULL on submit | FR-013a |
| `cases.admin_edit_comment` NOT NULL when transitioning decided case to pending_review | FR-053 |
| `policy_requirements.description` NOT NULL, NOT EMPTY | FR-043 |
| `completeness_report_items.verdict` derived from score — not stored directly settable via API | FR-024 |
| `audit_logs` rows: no UPDATE, no DELETE | FR-058 |
| `refresh_tokens.revoked = TRUE` on logout | FR-006 |
| `users.is_active = FALSE` blocks authentication | FR-056 |
