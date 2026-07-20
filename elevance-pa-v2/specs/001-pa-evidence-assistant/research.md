# Research: Elevance PA Evidence Assistant (v2)

**Feature**: `001-pa-evidence-assistant`
**Date**: 2026-07-20
**Status**: Complete — all NEEDS CLARIFICATION items resolved prior to Phase 1

---

## 1. LLM & Embedding Selection

### Decision: phi4-mini (3.8B, Q4_K_M) via Ollama + nomic-embed-text for embeddings

**Rationale**:
- phi4-mini at Q4_K_M quantization fits in ~2.5–3 GB VRAM, leaving ~3 GB headroom on the RTX 3050 (6 GB) for nomic-embed-text (~275 MB) and EasyOCR peak load (~1 GB) to coexist without swapping.
- phi4-mini is specifically optimized for structured output tasks and instruction following at small scale — higher reliability on JSON-schema completion than llama3.2:3b in benchmarks at this quantization level.
- nomic-embed-text (768-dim) via the same Ollama daemon means one process, one GPU context, no separate embedding service container. `OLLAMA_MAX_LOADED_MODELS=2` keeps both models resident simultaneously.
- `OLLAMA_FLASH_ATTENTION=1` + `OLLAMA_KV_CACHE_TYPE=q8_0` compress the KV cache further — effective for long clinical note contexts without additional VRAM cost.

**Alternatives considered**:
- llama3.2:3b: lower JSON reliability at Q4; phi4-mini preferred per Constitution Principle IV ("reliability takes priority over accuracy").
- bge-large-en-v1.5 (1024-dim) via TEI container: removed in v2 to stay within 2-container ceiling (Principle XII). nomic-embed-text via Ollama is sufficient; 768-dim vectors produce indistinguishable retrieval quality at this document corpus size.
- Larger models (mistral-7b, llama3.1-8b): violate Principle IV and would OOM with embeddings + OCR coloaded.

---

## 2. OCR Pipeline Design

### Decision: PyMuPDF native extraction → EasyOCR GPU fallback, per-page gated on character count threshold

**Rationale**:
- PyMuPDF's `page.get_text()` is instant and free (no GPU). Only pages returning < ~20 stripped characters trigger the EasyOCR path.
- EasyOCR with `gpu=True` is initialized once and reused (lazy singleton) — model weights (~1 GB) stay in VRAM only while the OCR path is active, not for every document.
- Per-page gating means a 20-page document with 18 native-text pages and 2 scanned pages only invokes GPU OCR twice — minimal VRAM contention with the LLM.
- Each chunk stores `extraction_method: "native" | "ocr"` enabling the UI to tag OCR-sourced evidence (Principle V).

**Threshold**: `len(page.get_text().strip()) < 20` characters → treat as image page, rasterize at 150 DPI (`page.get_pixmap(dpi=150)`), run EasyOCR.

**Alternatives considered**:
- Tesseract (pytesseract, CPU): CPU-only, slower on large scanned documents. EasyOCR CUDA is faster and fits the available hardware.
- Always-OCR (no native check): defeats the purpose — most clinical PDFs are native-text. Running OCR on every page would add minutes to each document and drive VRAM contention with the LLM.

---

## 3. Vector Store Design

### Decision: Qdrant `pa-evidence` collection with named vectors (dense + sparse), `case_id` payload filter

**Rationale**:
- Qdrant supports multiple named vectors per point natively (since v1.2). One collection, two named vector spaces: `"dense"` (768-dim, cosine) and `"sparse"` (BM25 via `qdrant/bm25` sparse model).
- All searches are filtered by `case_id` in the payload so results are never cross-contaminated between cases.
- Sparse/BM25 via Qdrant's native sparse vector support requires no additional process — it's a statistical model, not a neural encoder. Effectively free to run alongside the dense index.
- CPU indexing only (Qdrant standard image, not GPU image) — GPU HNSW indexing would compete with Ollama + OCR for the same 6 GB VRAM for no real benefit at this corpus size (hundreds of chunks, not millions).

**Collection schema**:
```
Point payload fields: case_id (UUID), document_id (UUID), chunk_id (UUID),
                      page_number (int), chunk_index (int), text (str),
                      extraction_method ("native"|"ocr")
Named vectors:
  dense:  dim=768, distance=Cosine
  sparse: sparse (BM25 via Qdrant sparse vector support)
```

**Alternatives considered**:
- Separate collections per case: operationally complex, collection proliferation at scale.
- Elasticsearch for BM25: would require a third always-on container, violating Principle XII.

---

## 4. Hybrid Retrieval Routing

### Decision: Three-path router (identifier → PostgreSQL/BM25; narrative → dense; mixed → RRF + keyword-miss cap)

**Rationale**:
- `PolicyRequirement.requirement_type` field (`"identifier"` | `"narrative"` | `"mixed"`) is set by the IntakeClassificationAgent during policy ingestion and drives retrieval routing at pipeline time.
- **Identifier path**: Exact match on PostgreSQL indexed columns (`cases.member_id`, `cases.cpt_hcpcs_code`, `cases.icd10_code`). If the identifier only appears inside scanned document text (not in case metadata), fall back to Qdrant BM25 sparse search.
- **Narrative path**: Qdrant dense vector search (nomic-embed-text embeddings), top-10 results, passed to PolicyReasoningAgent.
- **Mixed path**: Dense top-10 + BM25 sparse top-10 → RRF fusion (`score = 1/(60+dense_rank) + 1/(60+sparse_rank)`) → top-5 to reasoning agent. **Keyword-miss cap**: if the #1 RRF chunk has zero BM25 score on an identifier-bearing requirement, verdict is capped at "Unclear" regardless of dense confidence (prevents false-positive "Present" verdicts on identifier fields).

**Alternatives considered**:
- Always-fuse both paths: slower, unnecessary for pure identifier requirements where an exact DB lookup is faster and more precise.
- LangChain/LlamaIndex for orchestration: removed (custom zero-dependency pipeline, simpler to reason about on a single-box deployment with no distributed state).

---

## 5. Nurse Case Locking

### Decision: Heartbeat-based `last_active_at` timestamp, background expiry sweep every 60 seconds

**Rationale**:
- Frontend sends `POST /api/v1/nurse-review/cases/{id}/heartbeat` every 120 seconds while a case is open.
- Backend updates `cases.lock_last_active_at = now()` in PostgreSQL on each heartbeat.
- A background asyncio task (alongside the SLA service) sweeps every 60 seconds: `WHERE claimed_by_id IS NOT NULL AND lock_last_active_at < now() - INTERVAL '30 minutes'` → releases lock, writes AuditLog entry.
- No mouse-tracking, no WebSocket required. Fails obviously: a missed heartbeat just extends the effective timeout slightly (at most one extra sweep cycle = 60s beyond the 30-min threshold), acceptable.
- Race condition prevention: `UPDATE cases SET claimed_by_id = $nurse_id, claimed_at = now(), lock_last_active_at = now() WHERE id = $case_id AND claimed_by_id IS NULL` — atomic claim using a conditional UPDATE, not a separate SELECT + UPDATE.

**Alternatives considered**:
- Redis TTL-based locks: requires a third process, violates Principle XII.
- WebSocket for lock management: adds stateful connection overhead for a non-real-time use case.

---

## 6. Token / Session Management

### Decision: Stateless JWT (15-min access) + stored hashed refresh token (7-day, server-side revocation)

**Rationale**:
- Access tokens: signed HS256 JWTs with claims `{sub, role, exp, iat}`. No database lookup on each request — decoded and verified in the FastAPI dependency.
- Refresh tokens: UUID stored in `refresh_tokens` table as `argon2(token_value)` with `user_id`, `expires_at`, `revoked` columns. On logout, `revoked = TRUE`. On use, token is rotated (old record revoked, new record created).
- 15-minute access token blast radius is acceptable for an internal LAN-only staff tool (Constitution clarification, 2026-07-20 session).
- No token blacklist table needed — access tokens short-lived, refresh tokens server-side revocable.

**Alternatives considered**:
- Short-lived access + blacklist: unnecessary complexity; 15-min expiry achieves comparable security.
- OIDC / external IdP (Keycloak, Entra ID): 500 MB–1 GB RAM idle; violates Principle XII footprint intent.

---

## 7. Admin Edit → Re-Review Workflow

### Decision: `case_status_history` append-only table + `cases.admin_edit_comment` field

**Rationale**:
- When an admin edits a decided case, the system:
  1. Inserts a row into `case_status_history` recording the prior status, decision, decided_by, decided_at (snapshot).
  2. Updates `cases` fields (new values + `status = "pending_review"`, `admin_edit_comment = <comment>`, `admin_edit_by = <admin_id>`, `admin_edit_at = now()`, clears `claimed_by_id`).
  3. Writes an `AuditLog` entry of type `admin_case_edit` with before/after snapshot.
- The original nurse decision is never overwritten — it lives in `case_status_history` and `audit_logs`.
- The `"Admin Edit"` badge in the nurse queue is driven by `cases.admin_edit_comment IS NOT NULL AND cases.status = "pending_review"`.

**Alternatives considered**:
- Separate `case_revisions` table with full field snapshots: over-engineered for a small-team internal tool; `case_status_history` + `audit_logs` covers auditing needs.
- Overwriting `cases.review_status` without history: violates Constitution Principle X.

---

## 8. SLA Escalation

### Decision: Single Nurse Review queue, `is_escalated` boolean, escalated-first sort

**Rationale**:
- The SLA background service (inherited from v1) runs every 5 minutes. When `now() - cases.entered_review_at > policy.sla_hours` (default 48h): sets `cases.is_escalated = TRUE`, writes AuditLog `action_type = sla_escalation`.
- No separate escalation queue — Constitution clarification 2026-07-20. Queue API endpoint sorts: `ORDER BY is_escalated DESC, entered_review_at ASC`.
- Admin All Cases view exposes `is_escalated` as a filterable column.

---

## 9. Pipeline Error Handling

### Decision: Retry-with-backoff (3 attempts), then `Pipeline Error` terminal status surfaced via polling

**Rationale**:
- PolicyReasoningAgent retries up to 3 times with 30-second backoff on `ReadTimeout` / HTTP 5xx from Ollama (inherited from v1 resilience design).
- After 3 failures, `cases.status = "pipeline_error"` — surfaced to the intake associate via FR-018 polling without a manual page refresh.
- Admin can see pipeline-error cases in All Cases table and trigger a manual re-run via `POST /api/v1/admin/cases/{id}/rerun-pipeline`.

---

## 10. StorageService Abstraction

### Decision: Local filesystem implementation behind a `StorageService` protocol interface

**Rationale**:
- `StorageService` is a Python Protocol (structural typing) with methods: `save(case_id, doc_id, file_bytes) → str`, `load(path) → bytes`, `delete(path)`, `stream(path) → AsyncIterator[bytes]`.
- Local implementation: stores files at `DATA_DIR/documents/{case_id}/{doc_id}.pdf`.
- `DATA_DIR` comes from `secrets.py` / config, never hardcoded.
- Swap to MinIO/S3 implementation later by implementing the same protocol — no business logic changes needed.

---

## 11. Frontend Polling & Lock Heartbeat

### Decision: `usePolling` hook (5-10s, exponential backoff on error) + `useLockHeartbeat` hook (120s fixed)

**Rationale**:
- `usePolling(caseId, interval=7000)`: polls `GET /api/v1/cases/{id}/status` while `status === "processing"`. Stops when status resolves. On 3 consecutive errors, shows a "Connection issue — retrying" toast and backs off to 30s.
- `useLockHeartbeat(caseId)`: fires `POST /api/v1/nurse-review/cases/{id}/heartbeat` every 120 seconds while the case detail view is mounted. On unmount, does NOT send an explicit unlock (lock auto-expires); nurse can explicitly "Release" via a button which calls `DELETE /api/v1/nurse-review/cases/{id}/lock`.
- No global WebSocket infrastructure needed for either concern.
