# Tasks: Elevance Prior Authorization Evidence Assistant (v2)

**Input**: Design documents from `specs/001-pa-evidence-assistant/`

**Build order** (user-specified): Infra → Auth → Storage → Extraction → Policy Mgmt → Case Mgmt → Retrieval → Reasoning+Summary → Nurse Review → Admin → Frontend Shell

**User stories** (from spec.md):
- US1 – Intake Associate Creates a PA Case (P1 🎯 MVP)
- US2 – Nurse Reviews a Case and Makes a Decision (P1 🎯 MVP)
- US3 – Admin Uploads and Edits a Policy (P2)
- US4 – Admin Edits a Decided Case and Re-Routes (P2)
- US5 – Admin Manages Staff Accounts and Views Audit Log (P3)

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel with other [P] tasks in the same phase
- **[Story]**: User story this task directly enables
- All paths relative to repo root

---

## Phase 1: Setup — Infrastructure (Module 1)

**Purpose**: Spin up the two always-on Docker services, configure Ollama on the Windows host, and establish the Alembic baseline so every subsequent module has a working database and inference layer.

- [ ] T001 Create `backend/docker-compose.yml` with exactly two services: `postgres` (postgres:16-alpine, port 5432, volume `pgdata`) and `qdrant` (qdrant/qdrant:latest, ports 6333/6334, volume `qdrant_storage`); no other services
- [ ] T002 Create `backend/.env.local` template with all required variables: `DATABASE_URL`, `QDRANT_HOST`, `QDRANT_PORT`, `JWT_SECRET_KEY`, `OLLAMA_BASE_URL`, `DATA_DIR`, `ARGON2_TIME_COST`, `ARGON2_MEMORY_COST`, `ARGON2_PARALLELISM`; add to `.gitignore`
- [ ] T003 [P] Create `backend/scripts/setup_ollama.ps1`: verify Ollama is running at `OLLAMA_BASE_URL`, pull `phi4-mini` (Q4_K_M) and `nomic-embed-text` via `ollama pull`, set `OLLAMA_FLASH_ATTENTION=1` and `OLLAMA_KV_CACHE_TYPE=q8_0` in the Windows environment, verify both models respond to a smoke-test `/api/generate` call
- [ ] T004 [P] Create `backend/src/core/config.py` using `pydantic-settings`: load all variables from `.env.local`; expose typed settings singleton; no raw `os.environ` calls anywhere outside this file
- [ ] T005 [P] Create `backend/src/core/secrets.py`: thin abstraction over `config.py` that is the sole import for credentials throughout the codebase; exports `get_db_url()`, `get_jwt_key()`, `get_ollama_url()`, `get_qdrant_host()`, `get_data_dir()`, `get_argon2_params()`
- [ ] T006 Create `backend/alembic/` directory: run `alembic init alembic`, configure `env.py` to read `DATABASE_URL` via `secrets.get_db_url()` using async engine, set `target_metadata` to the shared `Base.metadata`
- [ ] T007 Create `backend/src/models/__init__.py` with `Base = declarative_base()` and `metadata = Base.metadata`; import all model modules here so Alembic auto-detects every table
- [ ] T008 Create `backend/main.py`: FastAPI app with `lifespan` context manager (startup: verify DB connection, verify Qdrant collection exists, log Ollama reachability); mount all routers under `/api/v1`; set CORS for `localhost:5173`

**Checkpoint**: `docker-compose up -d` starts postgres + qdrant; `python scripts/setup_ollama.ps1` succeeds; `alembic upgrade head` runs without error (no tables yet — baseline only)

---

## Phase 2: Foundational — Auth (Module 2)

**Purpose**: Every route in the system must have auth before any business logic is written. Build the complete auth layer first so all subsequent modules can simply attach `require_role(["nurse"])` and be secure by default.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete. Every route added in Phases 3+ must import and use `require_role`.

- [ ] T009 [P] Create `backend/src/models/user.py`: `User` SQLAlchemy model with columns `id` (UUID PK), `username` (VARCHAR 100, unique), `full_name` (VARCHAR 200), `hashed_password` (TEXT), `role` (ENUM intake/nurse/admin), `is_active` (BOOL default TRUE), `created_at`, `created_by_id` (FK self-ref nullable); `RefreshToken` model with `id`, `user_id`, `token_hash`, `expires_at`, `revoked`, `created_at`; `LoginAttempt` model with `id`, `username`, `attempted_at`, `success` (BOOL)
- [ ] T010 Create `backend/alembic/versions/0001_users_and_refresh_tokens.py`: Alembic migration creating `users`, `refresh_tokens`, and `login_attempts` tables with all indexes (`username` unique, `role`, `user_id`, `revoked`, `expires_at`, `login_attempts.username`); run `alembic upgrade head`
- [ ] T011 [P] Create `backend/src/core/security.py`: `hash_password(plain)` and `verify_password(plain, hashed)` using `passlib[argon2]` with params from `secrets.get_argon2_params()`; `create_access_token(sub, role, expires_delta=15min)` and `decode_access_token(token)` using `python-jose` HS256 with key from `secrets.get_jwt_key()`; `generate_refresh_token()` returns opaque UUID; `hash_refresh_token(raw)` via argon2
- [ ] T012 [P] Create `backend/src/core/database.py`: async SQLAlchemy engine using `asyncpg` driver from `secrets.get_db_url()`; `AsyncSessionLocal` factory; `get_db()` FastAPI dependency yielding session
- [ ] T013 Create `backend/src/core/dependencies.py`: `get_current_user(token: OAuth2PasswordBearer, db: AsyncSession)` — decode JWT, look up active user; `require_role(roles: list[str])` — returns FastAPI `Depends` that calls `get_current_user` then checks `user.role in roles`, raises HTTP 403 if not; `get_db` re-exported here for convenience
- [ ] T014 Create `backend/src/api/auth.py`: `POST /api/v1/auth/token` (OAuth2 password grant — check `COUNT(*) WHERE username=? AND success=false AND attempted_at > now() - 15min`, if ≥5 reject 429; insert `LoginAttempt`; verify username/password/is_active, issue JWT + refresh token, store hashed refresh token in DB, write `user_login` audit log); `POST /api/v1/auth/refresh` (verify refresh token hash, check not revoked/expired, rotate — revoke old, issue new); `POST /api/v1/auth/logout` (revoke refresh token by setting `revoked=TRUE`, write `user_logout` audit log); attach router to `main.py`
- [ ] T015 Create `backend/scripts/seed_admin.py`: CLI script (`python scripts/seed_admin.py --username admin --password X --full-name "Admin"`) that creates the first admin user directly in DB using `security.hash_password()`; idempotent (skips if username already exists)
- [ ] T016 [P] Create `backend/src/services/audit_service.py`: `log_event(db, event_type, actor_id, actor_role, case_id, payload)` — always an INSERT, never UPDATE/DELETE; used by all subsequent modules; corresponding `AuditLog` SQLAlchemy model in `backend/src/models/audit.py` with columns per data-model.md
- [ ] T017 Create `backend/alembic/versions/0002_audit_logs.py`: migration creating `audit_logs` table with indexes on `event_type`, `actor_id`, `case_id`, `created_at`; run `alembic upgrade head`

**Checkpoint**: `POST /api/v1/auth/token` with seeded admin credentials returns `access_token` + `refresh_token`; `GET /api/v1/cases` without token returns 401; with a nurse token returns 403 (route does not exist yet — 404 acceptable at this phase); `POST /api/v1/auth/logout` with valid refresh token returns 204; subsequent `/refresh` with the same token returns 401

---

## Phase 3: Foundational — Storage & Extraction (Modules 3 & 4)

**Purpose**: Storage abstraction and the text-extraction pipeline are shared infrastructure consumed by both Policy Management (US3) and Case Management (US1). Build them before either business module.

- [ ] T018 [P] Create `backend/src/services/storage_service.py`: `StorageService` Python Protocol with methods `save(case_id, doc_id, file_bytes) → str`, `load(path) → bytes`, `delete(path)`, `async_stream(path) → AsyncIterator[bytes]`; implement `LocalStorageService` storing files at `{DATA_DIR}/documents/{case_id}/{doc_id}.pdf`; create `DATA_DIR` on startup if absent; expose `get_storage_service()` FastAPI dependency returning the local implementation
- [ ] T019 [P] Create `backend/src/services/extraction_service.py`: `extract_pages(file_bytes: bytes) → list[PageExtraction]` where `PageExtraction = {page_number: int, text: str, extraction_method: "native"|"ocr", extraction_failed: bool}`; use `PyMuPDF (fitz)` for native extraction first (`page.get_text().strip()`); if `len(text) < 20` characters trigger EasyOCR GPU fallback (`easyocr.Reader(['en'], gpu=True)` lazy singleton, rasterize at 150 DPI via `page.get_pixmap(dpi=150)`); if EasyOCR also fails set `extraction_failed=True`, text=""
- [ ] T020 Create `backend/src/services/chunking_service.py`: `chunk_pages(pages: list[PageExtraction]) → list[Chunk]` splits each page's text into chunks of max 512 tokens with 50-token overlap (use `tiktoken` or character approximation); each chunk carries `page_number`, `chunk_index`, `text`, `extraction_method` (inherited from source page), `extraction_failed`; never splits a chunk across two pages

**Checkpoint**: `extraction_service.extract_pages()` on a native-text PDF returns all pages with `extraction_method="native"`; on an image-only PDF returns pages with `extraction_method="ocr"` and non-empty text; `chunking_service.chunk_pages()` produces chunks ≤ 512 tokens, each with correct `page_number` and `extraction_method` provenance

---

## Phase 4: User Story 3 — Policy Management (Module 5) (Priority: P2)

**Goal**: Admin can upload a policy PDF, receive an AI-generated requirement checklist, add/edit/delete rows, save, and overwrite on re-upload with same name. Intake/nurse can view policies read-only.

**Independent Test**: An admin uploads `lumbar_spine_policy.pdf` with name "Lumbar Spine MRI — 2026", sees the AI-generated checklist, adds one row, deletes one row, saves — and the policy appears in `GET /api/v1/policies` for all roles. Re-uploading under the same name replaces the checklist. A nurse token gets 403 on the upload and save endpoints.

- [ ] T021 [P] [US3] Create `backend/src/models/policy.py`: `Policy` SQLAlchemy model (`id`, `name` unique, `file_path`, `sla_hours` default 48, `is_deleted` BOOL default FALSE, `created_by_id`, `created_at`, `updated_at`); `PolicyRequirement` model (`id`, `policy_id` FK cascade delete, `description`, `requirement_type` ENUM identifier/narrative/mixed, `matching_criteria` JSONB nullable, `display_order`)
- [ ] T022 [US3] Create `backend/alembic/versions/0003_policies_and_requirements.py`: migration for `policies` and `policy_requirements` tables with indexes (`name` unique case-insensitive, `policy_id`, `requirement_type`); run `alembic upgrade head`
- [ ] T023 [US3] Create `backend/src/agents/intake_agent.py` — requirement-extraction pass: `extract_policy_requirements(text: str) → list[DraftRequirement]` calls Ollama `phi4-mini` with JSON-mode prompt asking it to return a structured list of requirements with `description` and `requirement_type` ("identifier" | "narrative" | "mixed"); retry up to 3 times on malformed JSON; returns empty list on total failure (never raises)
- [ ] T024 [US3] Create `backend/src/api/policies.py` with all five policy endpoints; enforce `require_role(["admin"])` on upload (`POST /api/v1/policies/upload`), draft-requirements (`GET .../draft-requirements`), and save (`POST .../requirements`) and delete (`DELETE /{policy_id}`); enforce any-authenticated-role on list (`GET /api/v1/policies`) and detail (`GET /{policy_id}`):
  - `POST /api/v1/policies/upload`: save PDF via StorageService; if `name` matches existing policy record update it (overwrite path), else create new; trigger background task `_extract_policy_requirements_task`; write `policy_created` audit log
  - `GET /api/v1/policies/{policy_id}/draft-requirements`: poll extraction status from DB; return draft requirement list
  - `POST /api/v1/policies/{policy_id}/requirements`: delete existing `policy_requirements` rows for this policy, bulk-insert the admin's finalized list; write `policy_requirement_saved` audit log
  - `GET /api/v1/policies` + `GET /api/v1/policies/{policy_id}`: read-only, any role; `GET /api/v1/policies` MUST filter `WHERE is_deleted = false`
  - `DELETE /api/v1/policies/{policy_id}`: admin only; soft-delete policy via `UPDATE policies SET is_deleted = true WHERE id = {policy_id}` (cases retain their evidence snapshot)
- [ ] T025 [US3] Implement background task `_extract_policy_requirements_task(policy_id, file_path, db)` in `policies.py`: call `extraction_service.extract_pages()` + `chunking_service.chunk_pages()` on the policy PDF; concatenate page texts; call `intake_agent.extract_policy_requirements(full_text)`; store draft results as `draft_requirements` in a `policy.draft_json` JSONB column; set `extraction_status = "complete"` or `"error"`
- [ ] T026 [US3] Add `draft_json` and `extraction_status` columns to `policies` table via `backend/alembic/versions/0004_policy_draft_columns.py`; run `alembic upgrade head`

**Checkpoint**: US3 Independent Test passes. `GET /api/v1/policies` returns saved policy for nurse token. `POST /api/v1/policies/upload` with nurse token returns 403.

---

## Phase 5: User Story 1 — Case Management (Module 6) (Priority: P1 🎯 MVP)

**Goal**: Intake associate uploads PDFs, receives AI-extracted field suggestions (nulls for unconfident fields), completes the case form with pre-filled values, selects policy by name, submits.

**Independent Test**: Upload `sample_clinical_note.pdf`; `extracted_fields.member_id.value = "M123456"`, `ai_extracted = true`; `icd10_code.value = null`; submit case with member_id + requested_service filled; case appears in list with `status = "processing"`; pipeline starts (verified by audit log `pipeline_started` event).

- [ ] T027 [P] [US1] Create `backend/src/models/case.py`: `Case` SQLAlchemy model with all columns per data-model.md (member_id NOT NULL, requested_service NOT NULL; provider_name/cpt_hcpcs_code/icd10_code/requested_date nullable; policy_id FK; status ENUM; is_escalated; claimed_by_id; claimed_at; lock_last_active_at; decided_by_id; decided_at; decision; admin_edit_by_id; admin_edit_at; admin_edit_comment; entered_review_at; created_at); `CaseStatusHistory` model (id, case_id, from_status, to_status, actor_id, actor_role, decision, comment, transitioned_at)
- [ ] T028 [P] [US1] Create `backend/src/models/document.py`: `Document` SQLAlchemy model (id, case_id FK cascade, original_filename, file_path, page_count nullable, uploaded_by_id, uploaded_at)
- [ ] T029 [US1] Create `backend/alembic/versions/0005_cases_documents_history.py`: migration creating `cases`, `case_status_history`, `documents` tables with all indexes (status, is_escalated, claimed_by_id, policy_id, created_at, entered_review_at, case_id); run `alembic upgrade head`
- [ ] T030 [US1] Add `extract_case_fields(text: str) → CaseFieldExtractions` to `backend/src/agents/intake_agent.py`: JSON-mode Ollama call returning structured object `{member_id, provider_name, cpt_hcpcs_code, icd10_code, requested_service, requested_date}` where each field is `{value: str|null, confident: bool}`; a field with `confident=false` MUST return `value=null`; retry 3× on malformed JSON; return all-null object on total failure
- [ ] T031 [US1] Create `backend/src/api/cases.py` with intake endpoints; enforce `require_role(["intake","admin"])` on upload and create; enforce any-authenticated-role on list, detail, status:
  - `POST /api/v1/cases/upload-documents`: accept multipart PDF files; save each via StorageService under a temp session UUID; run `extraction_service.extract_pages()` + `chunking_service.chunk_pages()` per document; concatenate all text; call `intake_agent.extract_case_fields()`; return `upload_session_id`, `document_ids`, `extracted_fields`
  - `POST /api/v1/cases`: validate member_id and requested_service non-null (422 if absent); create `Case` record with `status="processing"`; move documents from session to case; trigger background `completeness_pipeline` task; write `case_created` + `document_uploaded` + `pipeline_started` audit events; return 202
  - `GET /api/v1/cases`: paginated list with filters (status, service_type, from_date, to_date); intake sees own cases, nurse/admin see all
  - `GET /api/v1/cases/{case_id}`: full detail including `completeness_report` (empty list if pipeline not yet complete)
  - `GET /api/v1/cases/{case_id}/status`: lightweight status poll for FR-018 polling (returns id, status, is_escalated only)
  - `GET /api/v1/policies` (alias for dropdown): any authenticated role; sorted by name
- [ ] T032 [US1] Create `backend/src/pipelines/completeness_pipeline.py` — background task skeleton: `run_pipeline(case_id, db)` sets `status="processing"`, calls retrieval → reasoning → summary agents in sequence (stubbed in this task — stubs return empty lists/empty string), sets `status="pending_review"` + `entered_review_at=now()` on success or `status="pipeline_error"` on exception after 3 retries; writes `pipeline_completed` or `pipeline_error` audit event; transitions recorded in `case_status_history`

**Checkpoint**: US1 Independent Test passes. `GET /api/v1/cases/{id}/status` returns `"processing"` immediately after submit; transitions to `"pending_review"` after pipeline stub completes. Polling every 7s in the frontend (verified manually) shows the status update.

---

## Phase 6: Retrieval Pipeline (Module 7) — fills in the pipeline skeleton

**Purpose**: Replace the Phase 5 pipeline stubs with real retrieval. US1 and US2 both depend on this.

- [ ] T033 [P] Create `backend/src/services/embedding_service.py`: `embed(text: str) → list[float]` — POST to `{OLLAMA_BASE_URL}/api/embeddings` with `model=nomic-embed-text`; assert output dimension == 768; retry 2× on timeout; raise on persistent failure
- [ ] T034 [P] Create `backend/src/services/qdrant_service.py`: on startup create `pa-evidence` collection if not exists (named vectors: `dense` dim=768 cosine, `sparse` BM25); `index_chunks(case_id, chunks: list[Chunk])` — for each chunk call `embedding_service.embed(text)` to get dense vector, compute BM25 sparse vector, upsert Qdrant point with payload `{case_id, document_id, chunk_id, page_number, chunk_index, text, extraction_method}`; `search_dense(case_id, query, top_k=10)` — filtered dense search; `search_sparse(case_id, query, top_k=10)` — BM25 filtered search
- [ ] T035 Create `backend/src/services/fusion_service.py`: `rrf_fuse(dense_results, sparse_results, k=60) → list[FusedResult]` — compute RRF score `1/(k+rank)` per result, merge and sort; `apply_keyword_miss_cap(fused: list[FusedResult], requirement_type: str) → bool` — returns True (cap applied) if `requirement_type in ("identifier","mixed")` and top result has zero sparse score; `keyword_miss_cap_verdict(confidence: float) → str` — if cap applied, cap verdict at "unclear" regardless of confidence
- [ ] T036 Create `backend/src/agents/retrieval_agent.py`: `retrieve_evidence(case_id, requirement: PolicyRequirement, db) → RetrievalResult`; route by `requirement.requirement_type`: "identifier" → try exact match on `cases` columns first (member_id, cpt_hcpcs_code, icd10_code), fall back to BM25 sparse search if no column match; "narrative" → dense search only; "mixed" → RRF fusion via `fusion_service`; return top chunks with `keyword_miss` flag
- [ ] T037 Wire `qdrant_service.index_chunks()` into `completeness_pipeline.py`: after case documents are saved, call `extraction_service.extract_pages()` on each document, chunk via `chunking_service`, batch-index all chunks to Qdrant, then call retrieval agent per requirement

**Checkpoint**: After submitting a case with `sample_clinical_note.pdf`, Qdrant `pa-evidence` collection shows indexed points filtered to the case_id. `qdrant_service.search_dense(case_id, "conservative therapy")` returns non-empty results with correct payload fields.

---

## Phase 7: Reasoning & Summary Agents (Module 8)

**Purpose**: Generate completeness verdicts and nurse-facing summaries. Completes the pipeline for US2.

- [ ] T038 [P] Create `backend/src/models/completeness.py`: `CompletenessReportItem` SQLAlchemy model (id, case_id FK, requirement_id FK, verdict ENUM present/absent/unclear, confidence_score FLOAT, supporting_chunks JSONB, reasoning_log TEXT, keyword_miss BOOL, created_at)
- [ ] T039 [P] Create `backend/alembic/versions/0006_completeness_report_items.py`: migration for `completeness_report_items` table with indexes (case_id, requirement_id, verdict); run `alembic upgrade head`
- [ ] T040 Create `backend/src/agents/reasoning_agent.py`: `evaluate_requirement(requirement: PolicyRequirement, retrieved_chunks: list[Chunk], case: Case) → VerdictResult`; call `phi4-mini` in JSON mode with prompt: policy requirement description, retrieved evidence excerpts, case structured fields; model returns `{confidence: float, reasoning: str}`; apply verdict bands: `>=0.85 → "present"`, `<0.70 → "absent"`, else `"unclear"`; if `keyword_miss=True` on identifier/mixed requirement, cap at `"unclear"`; retry 3× on malformed JSON; on total failure return confidence=0.0 → "absent"
- [ ] T041 Create `backend/src/agents/summary_agent.py`: `generate_case_summary(case: Case, report_items: list[CompletenessReportItem]) → str`; call `phi4-mini` with narrative prompt: case metadata + per-requirement verdicts; returns plain-English summary for nurse RAG Summary view; retry 2× on failure; return empty string on total failure (never raises)
- [ ] T042 Wire reasoning + summary agents into `completeness_pipeline.py`: after indexing, iterate over `policy.requirements`; for each call `retrieval_agent.retrieve_evidence()` then `reasoning_agent.evaluate_requirement()`; bulk-insert `CompletenessReportItem` rows; call `summary_agent.generate_case_summary()` and store result in `cases.case_summary` column; write `pipeline_completed` audit event with all confidence scores and model version in payload
- [ ] T043 Add `case_summary` column to `cases` table: `backend/alembic/versions/0007_case_summary_column.py`; run `alembic upgrade head`

**Checkpoint**: Submit a case linked to the Lumbar Spine policy. After pipeline completes, `GET /api/v1/cases/{id}` returns `completeness_report` with ≥ 1 item having a verdict of "present", "absent", or "unclear"; `case_summary` is a non-empty string; audit log contains `pipeline_completed` event with confidence scores.

---

## Phase 8: User Story 2 — Nurse Review (Module 9) (Priority: P1 🎯 MVP)

**Goal**: Nurse sees the queue, claims a case (exclusive lock + heartbeat), toggles between RAG Summary and Document Viewer, accepts or rejects.

**Independent Test**: Create nurse account via `seed_admin.py`-style script. Nurse logs in, `GET /api/v1/nurse-review/queue` returns a pending case. Nurse POSTs lock → receives `locked: true`. Second nurse POSTs lock → receives 409. First nurse POSTs heartbeat → `lock_last_active_at` updated. First nurse POSTs decision `accepted` → `GET /api/v1/cases/{id}` shows `decision="accepted"`, lock cleared. Case appears in `decided` list under "accepted".

- [ ] T044 [P] Create `backend/src/services/lock_service.py`: `acquire_lock(case_id, nurse_id, db) → LockResult` — atomic `UPDATE cases SET claimed_by_id=$nurse_id, claimed_at=now(), lock_last_active_at=now() WHERE id=$case_id AND (claimed_by_id IS NULL OR lock_last_active_at < now()-INTERVAL '30 minutes')` returns `locked=True` on success, `locked=False` with `locked_by_name` on conflict; `refresh_heartbeat(case_id, nurse_id, db)` — UPDATE `lock_last_active_at=now()` WHERE `claimed_by_id=$nurse_id`; `release_lock(case_id, nurse_id, db)` — clear claim fields, write `nurse_lock_released` audit event; `expire_stale_locks(db)` — bulk UPDATE releasing all locks where `lock_last_active_at < now()-INTERVAL '30 minutes'`, write `nurse_lock_expired` audit events
- [ ] T045 [P] Create `backend/src/services/sla_service.py`: Two separate asyncio background tasks (run alongside main app lifespan). 1) `sla_sweep_loop()`: sleeps 300s, queries cases where `status="pending_review"` AND `entered_review_at < now()-INTERVAL '{policy.sla_hours} hours'` AND `is_escalated=FALSE`; bulk-UPDATE `is_escalated=TRUE`; writes `sla_escalation` audit events. 2) `lock_expiry_loop()`: sleeps 60s, calls `lock_service.expire_stale_locks()`
- [ ] T046 Create `backend/src/api/nurse_review.py` with all nurse review endpoints; enforce `require_role(["nurse","admin"])` on all:
  - `GET /api/v1/nurse-review/queue`: unclaimed + caller's locked cases; ORDER BY `is_escalated DESC, entered_review_at ASC`; include `claimed_by_name`, `claimed_by_me` flag, `admin_edit_comment`
  - `POST /api/v1/nurse-review/cases/{id}/lock`: call `lock_service.acquire_lock()`; write `nurse_lock_acquired` audit event; return 409 with `locked_by` name if already locked
  - `POST /api/v1/nurse-review/cases/{id}/heartbeat`: call `lock_service.refresh_heartbeat()`; 403 if caller is not current lock holder
  - `DELETE /api/v1/nurse-review/cases/{id}/lock`: call `lock_service.release_lock()`; 403 if caller is not lock holder
  - `POST /api/v1/nurse-review/cases/{id}/decision`: validate caller holds lock; validate `decision in ("accepted","rejected")`; UPDATE `cases` (decision, decided_by_id, decided_at, status, clear lock fields); INSERT `case_status_history` row; write `nurse_decision` audit event; 403 if not lock holder
  - `GET /api/v1/nurse-review/decided`: filter by `decision` param, paginated
  - `GET /api/v1/documents/{doc_id}/stream`: load PDF bytes via `storage_service.async_stream()`; return `StreamingResponse(media_type="application/pdf")`; enforce any-authenticated-role
- [ ] T047 Register SLA and lock expiry loops in `main.py` lifespan startup using `asyncio.create_task()` for both `sla_sweep_loop()` and `lock_expiry_loop()`

**Checkpoint**: US2 Independent Test passes. Background lock expiry fires — manually setting `lock_last_active_at = now()-INTERVAL '31 minutes'` on a locked case and waiting ≤60s results in the lock being cleared. SLA sweep flags a case after `sla_hours` threshold.

---

## Phase 9: User Story 4 — Admin Case Edit & Re-Queue (Module 10, Part A) (Priority: P2)

**Goal**: Admin edits any case field. If case is decided, mandatory comment required; case re-queued with "Admin Edit" badge; original decision preserved in audit + history.

**Independent Test**: Accept a case as nurse. Admin PATCHes it without `admin_comment` → 422. Admin PATCHes with `admin_comment` → case `status="pending_review"`, `admin_edit_comment` non-null. `GET /api/v1/admin/cases/{id}/history` shows original "accepted" row. Nurse queue shows case with "Admin Edit" indicator.

- [ ] T048 Create `backend/src/api/admin.py` — case management section; enforce `require_role(["admin"])` on all admin endpoints:
  - `GET /api/v1/admin/cases`: full paginated table with filters (status, is_escalated, policy_id, from/to date, search); join `users` for `claimed_by_name`, `decided_by_name`
  - `PATCH /api/v1/admin/cases/{id}`: accept partial case field updates; if case `status in ("accepted","rejected")` and `admin_comment` missing → 422; if comment present: INSERT `case_status_history` snapshot, UPDATE case fields + set `status="pending_review"`, `admin_edit_by_id`, `admin_edit_at`, `admin_edit_comment`, clear `claimed_by_id`; if admin overrides a nurse lock at time of edit also write `nurse_lock_released` event; write `admin_case_edit` + `admin_case_requeued` audit events
  - `POST /api/v1/admin/cases/{id}/rerun-pipeline`: only if `status="pipeline_error"`; reset to `"processing"`, re-trigger `completeness_pipeline`; write audit event
  - `GET /api/v1/admin/cases/{id}/history`: return all `case_status_history` rows for case in chronological order

**Checkpoint**: US4 Independent Test passes. `GET /api/v1/admin/cases/{id}/history` shows at minimum: `processing→pending_review`, `pending_review→accepted`, `accepted→pending_review` (admin edit) rows. Original "accepted" row is immutable.

---

## Phase 10: User Story 5 — Admin User Management & Audit Log (Module 10, Part B) (Priority: P3)

**Goal**: Admin creates/deactivates/resets accounts; browses immutable audit log with full search.

**Independent Test**: Admin creates nurse account. New nurse logs in — can access queue. Admin deactivates account — nurse's next login returns 401. Admin searches audit log by case_id and sees all events in chronological order. No DELETE or PATCH on audit log succeeds.

- [ ] T049 [US5] Add user management endpoints to `backend/src/api/admin.py`; enforce `require_role(["admin"])`:
  - `GET /api/v1/admin/users`: paginated user list
  - `POST /api/v1/admin/users`: create user with hashed password; 409 if username exists; write `user_created` audit event
  - `PATCH /api/v1/admin/users/{id}`: update `is_active` and/or `new_password` (re-hash); write `user_deactivated` or `user_reactivated` audit event; on deactivation also revoke all non-expired refresh tokens for that user
- [ ] T050 [US5] Add audit log endpoint to `backend/src/api/admin.py`:
  - `GET /api/v1/admin/audit-log`: filter by `case_id`, `actor_id`, `event_type`, `from_date`, `to_date`; paginated (default page_size=50); join users table for `actor_name`; ORDER BY `created_at ASC`; no DELETE or PATCH endpoint exposed

**Checkpoint**: US5 Independent Test passes. Deactivated user's refresh tokens are revoked. No HTTP method on `/admin/audit-log` modifies or deletes entries.

---

## Phase 11: Frontend Shell (Module 11)

**Purpose**: React/Vite/TypeScript frontend with role-gated sidebar, all pages wired to backend, light Tailwind + shadcn/ui theme.

**Goal**: Complete functional UI for all five user stories. Independent test: each sidebar area loads without errors, role-gating redirects non-authorized users, and the full case lifecycle (upload → submit → nurse review → accept) can be completed end-to-end in the browser.

### 11A — Shell & Auth

- [ ] T051 Scaffold `frontend/` with `npm create vite@latest frontend -- --template react-ts`; install Tailwind CSS 3, shadcn/ui, lucide-react, axios; configure `vite.config.ts` proxy for `/api` → `localhost:8000`
- [ ] T052 [P] Create `frontend/src/services/api.ts`: base axios instance with `Authorization: Bearer <token>` header injected from `authStore`; response interceptor that calls `POST /auth/refresh` on 401 and retries the original request once; MUST use an in-flight-refresh promise (`let refreshPromise = null;`) so concurrent 401s await the same refresh call; on second 401 clear tokens and redirect to login
- [ ] T053 [P] Create `frontend/src/stores/authStore.ts`: zustand store holding `{accessToken, refreshToken, user: {id, fullName, role}}`; `login(username, password)`, `logout()`, `refreshAccessToken()` actions; persist tokens to `sessionStorage`
- [ ] T054 Create `frontend/src/pages/LoginPage.tsx`: form with username/password fields; calls `api.ts` token endpoint; on success populates authStore and redirects to role-appropriate home page; shows error on 401
- [ ] T055 Create `frontend/src/components/layout/Sidebar.tsx`: fixed left sidebar with role-gated navigation items: "Case Management" (intake+nurse+admin), "Nurse Review" (nurse+admin only), "Policy Management" (all roles, but intake/nurse see read-only label), "Admin" (admin only); active item highlighted; user name + role shown at bottom with Logout button
- [ ] T056 Create `frontend/src/components/layout/RoleGate.tsx`: wrapper component that redirects to login if unauthenticated, or shows "Access Denied" if authenticated but wrong role; wraps every page route
- [ ] T057 Set up React Router in `frontend/src/main.tsx`: routes `/login`, `/cases` (intake+nurse+admin), `/nurse-review` (nurse+admin), `/policies` (all), `/admin` (admin); all except `/login` wrapped in `<RoleGate>` with correct `allowedRoles`; default redirect by role on login

### 11B — Case Management UI (US1)

- [ ] T058 [P] [US1] Create `frontend/src/hooks/usePolling.ts`: generic hook `usePolling(fetchFn, intervalMs, stopCondition)`; polls every 7000ms while mounted and `stopCondition` is false; stops automatically when `stopCondition(data)` returns true (status is terminal); backs off to 30s after 3 consecutive errors
- [ ] T059 [P] [US1] Create `frontend/src/components/cases/CaseStatusBadge.tsx`: displays status pill (Processing=yellow spinner, Pending Review=blue, Pipeline Error=red, Accepted=green, Rejected=orange); "Admin Edit" secondary badge when `admin_edit_comment` is non-null
- [ ] T060 [US1] Create `frontend/src/pages/CaseManagementPage.tsx`: case list table with columns (Case ID, Member ID, Service, Policy, Status, Submitted); search/filter bar (status dropdown, date range); rows for "processing" cases use `usePolling` on the row's `status` endpoint to auto-update; "+ New Case" button opens `NewCaseForm`
- [ ] T061 [US1] Create `frontend/src/components/cases/NewCaseForm.tsx`: multi-step form — Step 1: PDF upload dropzone (multi-file); on upload call `POST /cases/upload-documents`; show per-field pre-fill results with "AI-extracted — please verify" label in amber for `ai_extracted=true` fields; blank fields for `value=null`; Step 2: review/edit fields (Member ID + Requested Service marked required with asterisk); policy dropdown (fetches `GET /api/v1/policies`, sorted by name, shows names only); Step 3: submit calls `POST /cases`; on 202 navigate to case list and start polling the new case row

### 11C — Nurse Review UI (US2)

- [ ] T062 [P] [US2] Create `frontend/src/hooks/useLockHeartbeat.ts`: hook activated when nurse opens a case detail; fires `POST /nurse-review/cases/{id}/heartbeat` every 120 seconds while component is mounted; stops on unmount (no explicit unlock — lock auto-expires); logs heartbeat errors as warnings without crashing the UI
- [ ] T063 [P] [US2] Create `frontend/src/components/shared/OcrTag.tsx`: small inline badge rendering "Extracted using OCR" in amber; rendered alongside any evidence excerpt where `extraction_method = "ocr"`
- [ ] T064 [P] [US2] Create `frontend/src/components/nurse/VerdictBadge.tsx`: renders Present (green), Absent (red), Unclear (amber) badge based on verdict string; never shows raw confidence score
- [ ] T065 [US2] Create `frontend/src/pages/NurseReviewPage.tsx`: tab bar with "Queue", "Accepted", "Rejected" tabs; Queue tab fetches `GET /nurse-review/queue`; escalated cases shown with a flame/alert icon; locked-by-other cases shown greyed with "Locked by [Name]" label and non-clickable; escalated cases sorted to top; "Accepted" and "Rejected" tabs fetch `/nurse-review/decided?decision=accepted/rejected`
- [ ] T066 [US2] Create `frontend/src/components/nurse/CaseDetailView.tsx`: mounts `useLockHeartbeat`; top section shows "Admin Edit" banner with comment if `admin_edit_comment` is set; toggle buttons "RAG Summary" / "Document Viewer"; Accept and Reject buttons (only enabled when caller holds the lock); clicking Accept/Reject calls `POST /nurse-review/cases/{id}/decision`; on success navigate back to Queue tab
- [ ] T067 [P] [US2] Create `frontend/src/components/nurse/RAGSummary.tsx`: shows AI case summary paragraph at top; below it a table of requirements with columns: Requirement Description, Verdict (VerdictBadge), Evidence Excerpt (with OcrTag if OCR-sourced), Source Page; empty state message when completeness_report is empty
- [ ] T068 [P] [US2] Create `frontend/src/components/nurse/DocumentViewer.tsx`: fetches `GET /documents/{doc_id}/stream` as blob URL; renders each document in a `<iframe>` or PDF.js viewer; prev/next page controls; shows extraction failure warning banner for any page where `extraction_failed=true`

### 11D — Policy Management UI (US3)

- [ ] T069 [P] [US3] Create `frontend/src/pages/PolicyManagementPage.tsx`: for nurse/intake: read-only list + policy detail with requirement rows (no upload/edit controls rendered); for admin: "Upload Policy" button visible; policy list table with name, requirement count, updated date
- [ ] T070 [US3] Create `frontend/src/components/policy/RequirementEditor.tsx`: admin-only editable table of draft requirements; each row has description text input, requirement_type dropdown (identifier/narrative/mixed); add row button; delete row button per row; "Save Checklist" button calls `POST /policies/{id}/requirements`. Before `POST /policies/upload` fires, if `GET /policies?name=X` returns an existing match, show a confirmation modal: "This will overwrite policy '[name]', last updated [date] by [admin]. Continue?" Canceling/navigating away aborts. Read-only variant used for nurse/intake

### 11E — Admin UI (US4 + US5)

- [ ] T071 [P] [US4] Create `frontend/src/pages/AdminPage.tsx`: tab bar with "All Cases", "Users", "Audit Log" tabs
- [ ] T072 [P] [US4] Create `frontend/src/components/admin/AllCasesTable.tsx`: full case table with claimed_by_name, decided_by_name, is_escalated highlight (amber row tint); filter bar (status, is_escalated toggle, policy, date range, search); clicking a case row opens `AdminCaseEditPanel`
- [ ] T073 [US4] Create `frontend/src/components/admin/AdminCaseEditPanel.tsx`: shows all editable case fields; if case `status` is "accepted" or "rejected" renders a mandatory comment textarea (blocks Save until non-empty); Save calls `PATCH /admin/cases/{id}`; on `requeued=true` response shows success toast "Case re-queued for nurse review with Admin Edit tag"; "Status History" collapsible section fetches `GET /admin/cases/{id}/history`
- [ ] T074 [P] [US5] Create `frontend/src/components/admin/UserManagement.tsx`: user list table; "Add User" button opens modal with username/full_name/password/role fields; deactivate toggle per user row; all calls to `/admin/users` endpoints
- [ ] T075 [P] [US5] Create `frontend/src/components/admin/AuditLogViewer.tsx`: table with event_type, actor_name, case_id (linked to case), timestamp, payload summary; filter bar (case_id, user, event_type, date range); no edit/delete controls rendered; paginated with page-size selector

---

## Phase 12: Polish & Cross-Cutting Concerns

- [ ] T076 [P] Add global error boundary in `frontend/src/main.tsx`: catches unhandled React render errors and shows "Something went wrong — please refresh" fallback page instead of blank screen
- [ ] T077 [P] Add FastAPI global exception handler in `backend/main.py`: catch unhandled exceptions and return structured `{"detail": "Internal server error", "trace_id": uuid}` JSON; never expose stack traces in production responses
- [ ] T078 [P] Configure structured logging in `backend/src/core/` using `structlog` or `logging.config`: include `trace_id`, `user_id`, `case_id` in every log line; log level INFO in production, DEBUG via env var
- [ ] T079 [P] Add OpenAPI metadata to all FastAPI routers: `tags`, `summary`, `response_model`, `responses` (401, 403, 422) on every endpoint; verify `GET /docs` renders a complete spec
- [ ] T080 Populate `backend/tests/fixtures/` with three test PDFs: `sample_clinical_note.pdf` (native text, Member ID + CPT), `sample_scanned_fax.pdf` (image-only page), `lumbar_spine_policy.pdf` (3+ extractable requirements); document fixture contents in `backend/tests/fixtures/README.md`
- [ ] T081 Run `quickstart.md` validation scenarios end-to-end; document results and any deviations; update `quickstart.md` with corrected commands if needed
- [ ] T081a Run extraction pipeline against CPT-27447 test fixtures (Phase 12 validation script); assert that ≥4 of 6 fields are successfully extracted per SC-001
- [ ] T081b Run end-to-end pipeline latency test (Phase 12 validation script); time the full pipeline execution from upload to completeness report generation; assert <5 minutes per SC-002/SC-003
- [ ] T082 Verify all 14 constitution gates still pass post-implementation: confirm no external API calls have been introduced (grep codebase for `requests.get`, `httpx.get` pointing to non-localhost), confirm exactly 2 Docker containers, confirm all routes use `require_role`, confirm no `os.environ` calls outside `config.py`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Infra)**: No dependencies — start immediately
- **Phase 2 (Auth)**: Depends on Phase 1 (needs DB engine + config)
- **Phase 3 (Storage + Extraction)**: Depends on Phase 1 only — can run in parallel with Phase 2
- **Phase 4 (Policy Mgmt / US3)**: Depends on Phases 2 + 3 (needs auth, storage, extraction)
- **Phase 5 (Case Mgmt / US1)**: Depends on Phases 2 + 3 (needs auth, storage, extraction, intake agent)
- **Phase 6 (Retrieval)**: Depends on Phase 5 (needs Case model + pipeline skeleton)
- **Phase 7 (Reasoning+Summary)**: Depends on Phase 6 (needs retrieval results)
- **Phase 8 (Nurse Review / US2)**: Depends on Phase 7 (needs completeness report complete)
- **Phase 9 (Admin Edit / US4)**: Depends on Phase 8 (needs nurse decisions to exist)
- **Phase 10 (User Mgmt+Audit / US5)**: Depends on Phase 2 (auth) — can start after Phase 2
- **Phase 11 (Frontend)**: Can start shell (11A) after Phase 2; feature UIs need corresponding backend complete
- **Phase 12 (Polish)**: After all phases complete

### User Story Dependencies

- **US1 (P1 🎯)**: Phases 1–3 complete → Phase 5 → Phase 6–7 (retrieval fills in pipeline)
- **US2 (P1 🎯)**: US1 complete + Phases 6–7 complete → Phase 8
- **US3 (P2)**: Phases 1–3 complete → Phase 4 (independent of US1/US2)
- **US4 (P2)**: US2 complete → Phase 9
- **US5 (P3)**: Phase 2 complete → Phase 10 (independent of US1–US4 except auth)

### Parallel Opportunities Within Phases

- Phase 1: T003, T004, T005 can run in parallel after T001–T002
- Phase 2: T009, T011, T012 can run in parallel; T016 in parallel with T010
- Phase 3: T018, T019 can run in parallel; T020 depends on T019
- Phase 5: T027, T028 can run in parallel; T030 in parallel with T027–T028
- Phase 11A: T052, T053 in parallel; T058, T059, T062, T063, T064 in parallel within their story groups
- Phase 12: T076, T077, T078, T079, T080 all in parallel

---

## Parallel Examples

```text
# Phase 3 parallel launch (after Phase 2 complete):
Task T018: backend/src/services/storage_service.py
Task T019: backend/src/services/extraction_service.py
# T020 starts after T019 completes

# Phase 5 parallel launch (models):
Task T027: backend/src/models/case.py
Task T028: backend/src/models/document.py

# Phase 11 parallel UI components (after 11A shell complete):
Task T058: frontend/src/hooks/usePolling.ts
Task T059: frontend/src/components/cases/CaseStatusBadge.tsx
Task T062: frontend/src/hooks/useLockHeartbeat.ts
Task T063: frontend/src/components/shared/OcrTag.tsx
Task T064: frontend/src/components/nurse/VerdictBadge.tsx
```

---

## Implementation Strategy

### MVP First (US1 + US2 only)

1. Phase 1: Infra → Phase 2: Auth → Phase 3: Storage + Extraction
2. Phase 5: Case Management (US1) with pipeline skeleton
3. Phase 6: Retrieval → Phase 7: Reasoning + Summary
4. Phase 8: Nurse Review (US2)
5. **STOP and VALIDATE**: run `quickstart.md` Scenarios 1–3; all assertions pass
6. Phase 11A + 11B + 11C: Frontend shell + Case UI + Nurse UI
7. Full browser end-to-end: upload → submit → nurse accept

### Incremental from MVP

8. Phase 4: Policy Management (US3) + Phase 11D: Policy UI
9. Phase 9: Admin Case Edit (US4) + Phase 11E Part A: Admin Case UI
10. Phase 10: User Mgmt + Audit Log (US5) + Phase 11E Part B: Admin User/Audit UI
11. Phase 12: Polish and constitution validation

---

## Notes

- All tasks must pass the relevant `quickstart.md` validation scenario before moving to the next phase
- Every new API endpoint MUST use `require_role([...])` — no exceptions (Constitution Principle III)
- Every schema change is a new Alembic migration — never edit an applied one (Principle XIV)
- `os.environ` calls are forbidden outside `backend/src/core/config.py` (Principle XIII)
- The two Docker containers (postgres, qdrant) are the only containerized services — Ollama and EasyOCR run natively on the Windows host GPU (Principle XII)
- No external API calls of any kind — all inference is via `localhost:11434` (Principle I)
