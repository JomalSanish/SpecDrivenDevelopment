# Elevance Prior Authorization Evidence Assistant — Rebuild Plan (v2)
### Lightweight, On-Prem, Spec-Kit Driven

**Target hardware:** RTX 3050 (**6 GB VRAM**), 12th-gen i5, 16 GB RAM, Windows/PowerShell
**This revision:** dialed the LLM back down to the 3–4B class per your preference (less GPU load, and with 6GB available you get comfortable headroom to keep the LLM, embeddings, and GPU OCR all resident at once — see Section 7), locked in the 30-min nurse lock timeout, made policy upload admin-only with a manual fallback path, defined the admin-edit-triggers-re-review workflow, set confidence bands to ≥85% Present / <70% Absent, and made OCR provenance visible in the nurse-facing UI. Section 8 is now a decisions log rather than open questions — everything from this round is resolved.

---

## 1. What's Changing vs. the v1 Build

| Area | v1 (dropped) | v2 (this plan) | Why |
|---|---|---|---|
| LLM | Ollama `llama3.1` (8B) | Ollama `phi4-mini` (3.8B, Q4, primary) / `llama3.2:3b` (alt) | Your call — a 3-4B model keeps GPU load light. On a 6 GB card this leaves ~3GB+ of free VRAM even with the model resident, which is what makes it comfortable to also keep embeddings and GPU OCR loaded at the same time (Section 7) rather than constantly swapping. |
| OCR | *(not present in v1)* | **EasyOCR (CUDA/GPU)**, only as a fallback when native text extraction is empty | Policy PDFs and clinical notes are usually text-native (PyMuPDF gets the text for free, no GPU needed). Faxes/scans aren't — those go through GPU OCR. Gating OCR behind a "did text-extraction actually work?" check means the GPU-hungry OCR model only loads when it's genuinely needed, minimizing contention with the LLM. |
| Embeddings | TEI container running `bge-large-en-v1.5` (1024-dim, own Docker service) | `nomic-embed-text` served **by Ollama itself** (768-dim, GPU-capable) | Removes an entire container/process. One Ollama daemon now serves both chat and embeddings, and with 6 GB VRAM there's enough room to keep both loaded (see Section 9). |
| Object storage | MinIO (S3-compatible container) | Local filesystem, abstracted behind a `StorageService` interface | Removes a container + its background reaper/lifecycle threads. Same interface means you can swap back to MinIO later with one class change if you outgrow local disk. |
| Vector DB | Qdrant (Docker) | Qdrant (Docker) — **kept**, already lightweight | Qdrant's Rust core is ~150–300 MB RAM idle; not worth removing. |
| Relational DB | PostgreSQL (Docker) | PostgreSQL (Docker) — **kept** | Needed for real concurrent writes (multiple nurses). SQLite is offered as a dev-only fallback below. |
| Docker services running at once | 5 (`postgres`, `minio`, `minio_init`, `qdrant`, `ollama`, `tei` — actually 6) | **2** (`postgres`, `qdrant`) + Ollama running natively (not in Docker) | Native Ollama on Windows uses the GPU driver directly and avoids Docker Desktop's WSL2 virtualization tax on VRAM. |
| Auth | (not yet built) | Self-issued JWT + OAuth2 password flow, no external IdP | Keycloak/Auth0-style IdPs cost 500 MB–1 GB RAM idle — not worth it for 3 roles on a single box. |

Net effect: you go from 5–6 always-on containers to 2, and from a scattered (LLM + separate embedding container + separate object-storage container) GPU/RAM footprint to a single Ollama process serving both the LLM and embeddings, plus on-demand GPU OCR — fitting comfortably inside your 6 GB VRAM and leaving your 16 GB system RAM for Docker Desktop, VS Code, and the browser.

---

## 2. Revised Technology Stack

| Layer | Component | Choice | Resource note |
|---|---|---|---|
| LLM inference | Ollama (native Windows install, not containerized) | `phi4-mini` (3.8B, Q4_K_M, primary) / `llama3.2:3b` (alt) | ~2.5–3 GB VRAM at Q4_K_M. With `OLLAMA_FLASH_ATTENTION=1` + `OLLAMA_KV_CACHE_TYPE=q8_0` this leaves comfortable headroom on your 6GB card for embeddings and GPU OCR to stay loaded alongside it. |
| OCR | Tesseract (CPU) or EasyOCR (GPU/CUDA) | **EasyOCR**, gated behind a "native text extraction failed" check | PyMuPDF extracts text natively first (free, instant, no GPU). Only pages that come back near-empty (scanned faxes, image-only PDFs) get rasterized and passed to EasyOCR on the GPU. UI shows a small "Extracted using OCR" tag on any evidence sourced this way, so nurses know it's a step removed from the original text. |
| Embeddings | Ollama (same daemon) | `nomic-embed-text` (768-dim, ~275 MB, GPU-capable) | With the LLM now only ~2.5–3 GB, `nomic-embed-text` and the LLM comfortably coexist loaded at the same time, with room left over for EasyOCR to also touch the GPU without contention (see Section 7 for exact VRAM budgeting and `OLLAMA_MAX_LOADED_MODELS` config). |
| Vector DB | Qdrant (Docker, single container) | v1.9+, one collection `pa-evidence`, dense vectors + optional sparse (BM25) vectors | ~150–300 MB RAM. |
| Structured keyword lookups | PostgreSQL indexed columns / `tsvector` | Exact identifier match (case ID, member ID, CPT/ICD, policy name) | No extra service — this is why you don't need a separate keyword engine. |
| Object storage | Local disk (`/data/documents/{case_id}/{doc_id}.pdf`) behind `StorageService` interface | Swappable to MinIO/S3 later without touching business logic | Zero extra RAM. |
| Relational DB | PostgreSQL 16-alpine (Docker) | Cases, policies, users, audit log | ~150–250 MB idle. |
| OCR | Tesseract (via `pytesseract`), CPU only | For scanned/faxed PDFs | Lightweight, no GPU. |
| Backend | FastAPI + async SQLAlchemy + Alembic | Same as v1 | Unchanged, already light. |
| Frontend | React + Vite + Tailwind CSS + shadcn/ui (light theme) + lucide-react icons | New UI shell (Section 5) | Frontend was never your bottleneck — the browser runs on the client, not the GPU box. |
| Auth | Self-hosted JWT + OAuth2 password-grant (FastAPI `OAuth2PasswordBearer`, `python-jose`, `passlib[argon2]`) | 3 roles: `intake`, `nurse`, `admin` | No IdP container. |

### Dev-only lighter alternatives (if 16 GB RAM ever feels tight while Docker Desktop + IDE + browser are all open)

| Instead of | Consider | Trade-off |
|---|---|---|
| PostgreSQL in Docker | SQLite (file-based, `aiosqlite`) | Fine for solo dev/demo; weaker under concurrent nurse writes — don't use in anything resembling production. |
| Qdrant server (Docker) | Qdrant **embedded mode** (`QdrantClient(path=...)`, runs in-process inside FastAPI, on-disk RocksDB) | Removes the container entirely; loses the ability to inspect/administer via a separate process while the app is running. |
| Docker Desktop overhead on Windows | WSL2 resource limits in `.wslconfig` (cap `memory=6GB`, `processors=4`) | Prevents Docker/WSL2 from silently eating RAM you need for Ollama. |

---

## 2a. OCR Pipeline Design

Both **case documents** (clinical notes, referrals, faxes) and **policy documents** need this — policy PDFs are usually text-native, but clinical faxes and scanned referrals often aren't, and you shouldn't have to know which is which ahead of time.

```
extract_text(pdf_bytes)
│
├── 1. Try native extraction first: PyMuPDF (fitz), page by page
│      → if page.get_text() returns a reasonable character count
│        (e.g. > ~20 chars per page after whitespace strip), keep it — no GPU used.
│
└── 2. If a page comes back empty/near-empty → it's an image (scan/fax):
       → Rasterize that page to an image (PyMuPDF's `page.get_pixmap()`, ~150-200 DPI)
       → Run EasyOCR (GPU) on the page image
       → Merge OCR text back into the document's page sequence, tagged
         `extraction_method: "ocr"` in the chunk metadata (useful later if a
         nurse ever needs to know a given passage came from OCR vs. native text —
         OCR text is inherently a little less trustworthy character-for-character).
```

This mixed-mode extractor plugs into the same place `pdf_service.py` occupied in v1 — nothing downstream (chunking, embedding, indexing) needs to know whether a given page was OCR'd or native.

**Why gate OCR behind a native-extraction check instead of always running it:** it's both faster (most pages never touch the GPU) and reduces VRAM contention with the LLM, which is the actual resource-constrained part of this system.

---

## 3. Auth Design (JWT + OAuth2)

- **Every role authenticates — no exceptions.** Intake, nurse, and admin all sign in through the same OAuth2 endpoint; there is no unauthenticated route or "internal" bypass anywhere in the API. Every route is guarded by both authentication (valid JWT) and authorization (correct role for that route).
- **Flow:** OAuth2 "password" grant (self-hosted — this is an internal staff app, not a public consumer login, so there's no need for a redirect-based Authorization Code flow or a third-party IdP).
- **Endpoints:** `POST /api/v1/auth/token` (username + password → `access_token` [JWT, 15 min] + `refresh_token` [7 days, rotated on use, stored server-side hashed]).
- **JWT claims:** `sub` (user id), `role` (`intake` | `nurse` | `admin`), `exp`, `iat`.
- **Password storage:** `argon2` via `passlib` — no separate service, memory-hard hashing.
- **RBAC:** a `require_role(["admin"])` FastAPI dependency guards `/api/v1/admin/*` and policy upload/edit routes; `require_role(["nurse","admin"])` guards `/api/v1/review/*`; `require_role(["intake","nurse","admin"])` guards general case-viewing routes — every endpoint declares its allowed roles explicitly rather than defaulting open.
- **If you ever need real SSO** (Entra ID/Okta) later, this design swaps in cleanly — you'd add an OIDC redirect flow that mints the same internal JWT format after federation, so nothing downstream changes.

---

## 4. Hybrid Retrieval Design

Your instinct — *identifiers need keyword match, case narrative needs semantic* — is exactly right, and it's actually **lighter** than a single always-fuse-both approach:

```
Requirement type?
├── Structured identifier (Case ID, Member ID, Policy name/ID, CPT/HCPCS, ICD-10)
│     → Exact/keyword match: PostgreSQL indexed column lookup (or Qdrant sparse/BM25
│       filter over chunk text if the identifier only appears inside a scanned note)
│     → No semantic search needed — cheapest, most precise path
│
└── Clinical/narrative requirement ("6 weeks conservative therapy", "neurological symptoms")
      → Semantic dense search: Qdrant vector search against nomic-embed-text embeddings
      → Top-k chunks → PolicyReasoningAgent
```

For requirements that are *mixed* (e.g., "does the note mention CPT 72148 was already denied"), keep the RRF fusion approach from your original `fusion_service.py` — dense + sparse, combined:

```
RRF(chunk) = 1 / (60 + dense_rank) + 1 / (60 + sparse_rank)
```

...and keep your existing `keyword_miss` guardrail: if a chunk scores well semantically but has **zero** keyword/BM25 hit on an identifier-bearing requirement, cap the verdict at **Unclear**, forcing nurse review rather than trusting a "confident-sounding but keyword-blind" LLM answer. That rule was good engineering in v1 — carry it forward unchanged.

**Sparse/BM25 vectors:** use Qdrant's native sparse vector support with `Qdrant/bm25` (a statistical model, not a neural one — effectively free to run) rather than adding a second neural encoder.

---

## 5. UI Specification — Sidebar Shell, Light Theme

**Visual language:** neutral light background (`#F7F8FA`), white content cards with a soft 1px border + subtle shadow, one accent color (blue/teal), Inter font, 8px spacing grid, fixed 240px sidebar with icon + label nav items, top bar with global search + user avatar/role badge.

**Sidebar sections** (top to bottom): Case Management · Nurse Review · Policy Management · Admin — each gated by role (an `intake` user won't see Admin; nurses can view Policy Management read-only to see requirement checklists, but only `admin` sees the upload/edit controls there).

### 5.1 Case Management
- **Case list** — searchable/filterable table (status, service type, created date).
- **"+ New Case"** flow:
  1. Upload document(s) first — the doc comes in before anything else.
  2. Backend runs the mixed-mode extractor (Section 2a: native text first, EasyOCR/GPU fallback for scans), then an LLM pass (`phi4-mini`, JSON mode) **searches the extracted text for**: Member ID, Provider, CPT/HCPCS, ICD-10, requested service/procedure, requested date. This is best-effort — whichever fields the model can confidently locate get filled in; any field it can't find is simply left blank rather than guessed, so the intake associate fills that one in manually.
  3. Form renders the found fields **pre-filled and visibly marked "AI-extracted — please verify"**; blank fields are visually identical to a normal empty field (no false confidence). Everything stays editable.
  4. **Policy** field is a searchable dropdown populated from `GET /api/v1/policies` (returns `{id, name}`), sorted and displayed **by name** — no one ever sees or types a policy ID.
  5. Submit → case created, pipeline kicked off as a background task (same fire-and-forget pattern as v1).

### 5.2 Nurse Review
Sub-tabs: **Queue** (unclaimed + assigned to you) · **Accepted** · **Rejected**.
- Case detail view has a toggle: **"RAG Summary"** (Agent-4 generated case summary + per-requirement completeness table, verdicts of Present ≥85% confidence / Absent <70% / Unclear in between) vs. **"View Documents"** (side-by-side PDF viewer, page-by-page, same as v1's `NurseReviewWorkspace`). Nurses can flip between them freely — the RAG report is a shortcut, not a replacement for the source PDFs. Any evidence chunk sourced via OCR carries a small **"Extracted using OCR"** tag so the nurse knows it's a step removed from the original text.
- **Lock button:** claims the case (`claimed_by_id`, `claimed_at`) so it disappears from other nurses' actionable queue (they still see it, greyed out, as "Locked by [Nurse Name]"). Auto-releases after **30 minutes** of inactivity — confirmed default.
- **Accept / Reject:** a human decision on *documentation completeness/routing*, never a clinical approval or denial. Decision + nurse ID + timestamp move the case into the Accepted/Rejected sub-tab.
- **Admin-edited cases reappear in the Queue** even if previously decided — shown with an **"Admin Edit"** badge and the admin's comment visible at the top of the case detail view, so the nurse immediately understands why a case they already handled is back.

### 5.3 Policy Management
- Upload is **admin-only** — intake and nurses can view the policy list and requirement checklists read-only, but only `admin` can upload, edit, or re-process a policy.
- Upload form: file + a required **"Policy Name"** text field entered by the admin.
- On submit, the same mixed-mode extractor + an LLM pass converts the policy into a structured requirement checklist, shown back to the admin for review.
- **Manual fallback:** if the extraction pass misses requirements or gets some wrong (a real possibility with a 3-4B model on a dense policy document), the admin can add, edit, or delete individual requirement rows directly in the checklist UI before saving — the AI extraction is a draft, not the final word.
- **Re-uploading a policy with a name that already exists overwrites it** (not versioned) — this is safe specifically because upload is admin-only, so there's a single accountable owner for each policy's content.
- List view of ingested policies with edit/re-process actions.

### 5.4 Admin
- **All Cases:** full table, filterable by status/queue, shows **Locked By** and **Decided By** columns, admin can edit fields and force-unlock/reassign a stuck case.
- **Editing a case that's already been accepted or rejected is allowed**, but doing so requires a comment (mandatory free-text field: "why is this being reopened") and automatically routes the case back into the Nurse Review Queue, tagged **"Admin Edit"** with the admin's name and comment attached, for a fresh nurse decision. The case's prior decision stays in the audit log — it isn't overwritten, just superseded.
- **Nurses:** list, active locks, case counts, decision history.
- **Policies:** full CRUD (upload/edit restricted to admin, per Section 5.3).
- **Users & Roles:** create/deactivate accounts, assign `intake`/`nurse`/`admin`, reset password.
- **Audit Log:** filterable by case/user/action — same immutable `audit_logs` table as v1, including admin-edit-reopen events.

---

## 6. Spec-Kit Implementation Plan — Complete Command Sequence

Spec-Kit's CLI moved from `--ai` to `--integration` in v0.10 — use the syntax below (current as of mid-2026). Run these **in order**, in a fresh repo, in Claude Code.

### 6.0 Install & init

```powershell
uv tool install specify-cli --from git+https://github.com/github/spec-kit.git
specify version
specify init elevance-pa-v2 --integration claude
cd elevance-pa-v2
```

### 6.1 `/speckit.constitution`

```
/speckit.constitution
This project is the Elevance Prior Authorization Evidence Assistant (v2 rebuild).

Non-negotiable constraints:
1. Zero external API calls. All LLM inference, embeddings, OCR, and storage run
   on-premises on a single Windows box (RTX 3050, 6GB VRAM, 12th-gen i5, 16GB RAM).
2. No automated clinical approval or denial, ever. Every case is routed
   unconditionally to human nurse review. There is no `human_review_required`
   boolean anywhere in the schema — routing to a human queue is the only path.
   A nurse's "accept"/"reject" action is a documentation-completeness and
   routing decision, never a clinical approval or denial.
3. Every role — intake, nurse, admin — authenticates and is authorized via
   our own JWT/OAuth2 password-grant endpoint. There is no unauthenticated
   route and no route without an explicit role check.
4. LLM sizing: use a 3-4B class model (phi4-mini or llama3.2:3b), not larger.
   Prefer a model configuration that always returns valid structured JSON
   and always completes over a larger/slower one, even at some cost to
   accuracy — reliability and low GPU load take priority.
5. Every document (case document or policy document) may be a native-text PDF
   or a scanned/faxed image. Text extraction must try native extraction
   (PyMuPDF) first per page, and only fall back to OCR (EasyOCR, GPU-accelerated)
   for pages that return near-empty text. Chunks must record whether their
   source text came from native extraction or OCR, and the nurse-facing UI
   must visibly tag any evidence sourced via OCR.
6. Case field auto-extraction is best-effort: extract whichever fields the
   model can confidently find in the uploaded document(s); leave any field
   it can't find blank for manual entry rather than guessing.
7. Completeness confidence bands: Present if >= 85% confidence, Absent if
   < 70% confidence, Unclear for everything in between.
8. Hybrid retrieval: structured identifiers (case ID, member ID, policy name,
   CPT/HCPCS, ICD-10) resolve via exact/keyword match against indexed
   PostgreSQL columns (or Qdrant sparse/BM25 when the identifier only appears
   inside free-text); clinical narrative requirements resolve via semantic
   dense vector search; mixed requirements use reciprocal rank fusion with a
   keyword-miss cap that forces an "Unclear" status when a semantically
   confident chunk has zero keyword corroboration on an identifier-bearing
   requirement.
9. Policy upload is admin-only. Policy extraction into a requirement
   checklist is AI-assisted but must support full manual add/edit/delete of
   requirement rows by the admin before saving. Re-uploading a policy with an
   existing name overwrites it (no versioning) — safe because only admins
   can upload policies.
10. Admin may edit any case, including ones already accepted or rejected.
    Editing a decided case requires a mandatory comment and automatically
    routes the case back into the nurse review queue, tagged "Admin Edit"
    with the admin's name and comment, for a fresh nurse decision. The
    original decision is preserved in the audit log, not overwritten.
11. Nurse case lock: 30-minute auto-release on inactivity.
12. Resource ceiling: at most 2 always-on Docker containers (postgres, qdrant).
    The LLM, the embedding model, and GPU-accelerated OCR all run through a
    natively-installed (non-containerized) process on the host so they can
    access the NVIDIA GPU directly rather than through Docker/WSL2 passthrough.
13. Secrets go through a single secrets-abstraction module, never raw
    os.environ calls.
14. Every schema change ships as an Alembic migration; never edit a migration
    that has already been applied.
```

### 6.2 `/speckit.specify`

```
/speckit.specify
Build the Elevance Prior Authorization Evidence Assistant: a payer-side web
app with four staff-facing areas behind a sidebar (Case Management, Nurse
Review, Policy Management, Admin), backed by a 5-agent RAG pipeline, running
entirely on-premises.

Roles: Intake Associate, Nurse, Admin — all three authenticate and are
authorized via our own JWT/OAuth2 password-grant endpoint. There is no
unauthenticated access path anywhere in the system.

Case Management: an intake associate uploads one or more documents first
(PDFs, which may be native-text or scanned/faxed images). The system
extracts text per page (native extraction first, OCR fallback for
image-only pages), then searches the extracted text with an LLM pass to
auto-fill whichever of these fields it can confidently find: member ID,
provider, CPT/HCPCS code, ICD-10 code, requested service/procedure, and
requested date. This is best-effort — fields it can't find are left blank
for manual entry rather than guessed. Found fields render pre-filled and
clearly marked as AI-extracted, editable before submission. The policy for
the case is chosen from a dropdown populated from all ingested policies,
sorted and displayed by policy name — the policy ID is never shown or typed.
On submit, the case is created and the completeness pipeline runs as a
background task.

Nurse Review: a nurse sees a queue of unclaimed cases and cases they have
personally claimed ("locked"), plus separate Accepted and Rejected tabs for
cases they've already decided. Locking a case sets it read-only for every
other nurse (shown to them as "locked by [name]") for up to 30 minutes of
inactivity, after which it auto-releases. Within a case, the nurse can
toggle between an AI-generated RAG summary (case summary + a per-requirement
completeness table showing Present/Absent/Unclear with supporting evidence
citations — Present at >=85% confidence, Absent below 70%, Unclear between)
and a manual document viewer (the original PDFs, page by page). Any evidence
sourced via OCR is visibly tagged "Extracted using OCR" wherever it's shown.
The nurse then accepts or rejects the case — a human decision about
documentation completeness and routing, never an automated or AI-driven
clinical approval or denial. If an admin later edits a case that was already
accepted or rejected, it reappears in that nurse's (or any nurse's) queue
tagged "Admin Edit" with the admin's comment, for a fresh decision.

Policy Management: upload, edit, and re-processing are admin-only; intake
and nurse roles can view policies and their requirement checklists
read-only. An admin uploads a policy document with a required policy name
field. The system runs the same text-extraction pipeline (native + OCR
fallback) and an LLM pass that converts the policy into a structured
requirement checklist. Because this extraction can miss or misread
requirements, the admin can manually add, edit, or delete individual
requirement rows before saving. Re-uploading a policy under an existing
name overwrites it (no versioning) — acceptable because only admins can
upload.

Admin: full visibility and edit access over all cases (including which
nurse has a case locked and which nurse decided it and how). Editing a
case that's already been decided requires a mandatory comment and
automatically re-routes it to nurse review, tagged with that comment; the
original decision is preserved in the audit log rather than overwritten.
Admin also manages nurse and other staff accounts and roles, has full CRUD
over policies, and can browse a searchable, immutable audit log of every AI
call, decision, and status change.

Retrieval must be hybrid: exact/keyword match for structured identifiers,
semantic vector search for clinical narrative requirements, and reciprocal
rank fusion with a keyword-miss guardrail for mixed requirements.

Reference material: I'm attaching architecture.md (our original 5-agent
architecture and data flow), Solution_Architecture.docx (enterprise
architecture reference), and Elevance_Sample_Usecase.docx (personas, sample
question/output table, in-scope/out-of-scope list) for grounding — use these
for the domain model, agent responsibilities, and sample interactions, but
apply the resource-constrained, on-prem stack from our constitution rather
than the cloud-neutral/multi-LLM-gateway version described in
Solution_Architecture.docx.
```

*(Attach the three files from this conversation — `architecture.md`, `Solution_Architecture.docx`, `Elevance_Sample_Usecase.docx` — when you run this command, so Claude Code has the original personas, sample Q&A table, and 5-agent responsibilities as source material.)*

### 6.3 `/speckit.clarify`

```
/speckit.clarify
```

The product-level ambiguities from the last round are now resolved and baked into the constitution/specify text above (lock timeout, admin-edit workflow, policy versioning, confidence bands, extraction field handling). Still run `/speckit.clarify` anyway — it's good practice to let it surface anything *technical* it finds ambiguous in the spec (e.g., exact API error-response shapes, pagination defaults) before planning.

### 6.4 `/speckit.plan`

```
/speckit.plan
Tech stack:
- Backend: Python, FastAPI, async SQLAlchemy, Alembic migrations.
- Database: PostgreSQL 16 (Docker container), storing cases, documents,
  policies, policy_requirements, completeness_report_items, users, audit_logs.
  Cases need a status history / re-review tracking table to support the
  admin-edit-reopens-for-review workflow without losing the prior decision.
- Object storage: local filesystem under a StorageService abstraction
  (interface-compatible with a future S3/MinIO swap), not MinIO directly.
- Vector DB: Qdrant (Docker container), one collection named "pa-evidence",
  storing dense vectors (from nomic-embed-text) and sparse/BM25 vectors,
  filtered by case_id per search, same as our v1 design.
- LLM + embeddings: Ollama, installed natively on Windows (not Dockerized),
  serving phi4-mini (3.8B, Q4_K_M) for reasoning/extraction/summarization
  and nomic-embed-text for embeddings, with OLLAMA_FLASH_ATTENTION=1 and
  OLLAMA_KV_CACHE_TYPE=q8_0 set. This model size is a deliberate choice to
  keep GPU load light, not a hardware limitation — we have headroom to
  spare on the 6GB card.
- OCR: PyMuPDF for native text extraction; EasyOCR (CUDA/GPU) as a
  per-page fallback when native extraction returns near-empty text. Chunks
  store an extraction_method field ("native" | "ocr") surfaced in the UI.
- Auth: FastAPI OAuth2PasswordBearer + python-jose for JWT signing +
  passlib[argon2] for password hashing. No external identity provider.
  Every route declares required role(s) explicitly.
- Frontend: React + Vite + TypeScript + Tailwind CSS + shadcn/ui, light
  theme, fixed sidebar with role-gated navigation (Case Management, Nurse
  Review, Policy Management, Admin). Policy Management is view-only for
  intake/nurse, edit-capable for admin only.
- Retrieval routing: identifier-type policy requirements resolve via
  PostgreSQL indexed-column exact match; narrative requirements resolve via
  Qdrant dense search; mixed requirements use RRF fusion of dense + sparse
  with the keyword-miss cap. Completeness verdicts use Present >= 85%
  confidence, Absent < 70%, Unclear in between.
- Case field extraction: best-effort per field, independently — a field the
  model can't confidently locate is left null, not guessed or defaulted.
- Docker Compose defines exactly two services: postgres and qdrant. Ollama
  and the OCR process run natively on the host.

Directory layout should mirror our v1 project (src/core, src/models,
src/agents, src/services, src/api, alembic/, frontend/src) since the module
boundaries (5 agents, completeness pipeline, SLA service) carry over
unchanged from the reference architecture — only the underlying model/
embedding/storage implementations and the admin-edit/re-review workflow are
new relative to v1.
```

### 6.5 `/speckit.checklist`

```
/speckit.checklist
Generate three checklists:
1. Security: JWT expiry and rotation correctness, argon2 configuration,
   RBAC coverage on every route with no route reachable without the correct
   role dependency (explicitly verify Policy Management write routes reject
   non-admin roles), refresh-token invalidation on logout/role change.
2. RAG/retrieval: chunking correctness across OCR/native boundaries,
   embedding dimension consistency end to end, keyword-miss guardrail
   present and tested, OCR fallback only triggers on genuinely empty pages
   (not falsely on sparse-but-valid text), confidence bands correctly applied
   (>=85% Present, <70% Absent, else Unclear).
3. UI/workflow: sidebar role-gating per page, lock/unlock race conditions
   (two nurses can't claim the same case), light-theme contrast and
   accessibility, Accepted/Rejected tab correctness after a decision,
   admin-edit-on-decided-case correctly re-routes to nurse queue with the
   "Admin Edit" tag and comment visible, policy re-upload-with-same-name
   correctly overwrites rather than duplicating.
```

### 6.6 `/speckit.tasks`

```
/speckit.tasks
Break the plan into tasks grouped by module, in this build order:
1. Infra: docker-compose.yml (postgres + qdrant only), native Ollama setup
   script pulling phi4-mini and nomic-embed-text, Alembic baseline migration.
2. Auth: user model + roles, OAuth2 token endpoint, JWT middleware,
   role-dependency helpers applied to every route.
3. Storage: StorageService local-disk implementation.
4. Text extraction: PyMuPDF native extraction, EasyOCR GPU fallback,
   per-chunk extraction_method metadata surfaced to the frontend as an
   "Extracted using OCR" tag.
5. Policy Management: admin-only upload endpoint, extraction-to-requirement-
   checklist agent pass, manual add/edit/delete of requirement rows,
   overwrite-on-same-name re-upload logic, policies-by-name listing endpoint
   (read-only for non-admin roles).
6. Case Management: upload endpoint, best-effort extraction agent for case
   metadata (nulls for fields it can't find, no guessing), pre-filled
   case-creation form, policy dropdown.
7. Retrieval: chunking service, Ollama embedding calls, Qdrant indexing,
   identifier-vs-narrative router, RRF fusion with keyword-miss cap.
8. Reasoning + Summary agents: completeness verdicts (Present >=85%,
   Absent <70%, else Unclear), nurse-facing case summary generation.
9. Nurse Review: queue endpoint, lock/unlock endpoints (30-min auto-release),
   RAG-summary vs. document-viewer toggle, accept/reject endpoints,
   Accepted/Rejected tabs.
10. Admin: all-cases table with locked-by/decided-by columns; edit capability
    on any case including already-decided ones, with mandatory comment and
    automatic re-routing to the nurse queue tagged "Admin Edit"; nurse/user
    management; policy CRUD; audit log viewer including re-review events.
11. Frontend shell: sidebar navigation, role-gated routing, light theme.
```

### 6.7 `/speckit.analyze`

```
/speckit.analyze
```

Run this after **every** module in Section 6.6, not just at milestones — this was your own best-practice finding on the v1 build, and it still holds here.

### 6.8 `/speckit.implement`

```
/speckit.implement
```

Don't let this run all 11 modules unattended in one shot. Implement Infra → Auth → Storage → Text extraction first, then stop and verify on your actual machine: confirm Ollama loads `phi4-mini` and responds within a reasonable time, and confirm EasyOCR actually engages the GPU (`nvidia-smi` should show it) before building the rest of the pipeline on top of it. Then continue module by module, running `/speckit.analyze` between each.

### 6.9 `/speckit.converge`

```
/speckit.converge
```

Run once all 11 modules are implemented and passing tests, as a final cross-artifact consistency pass before you consider the rebuild done.

---

## 7. GPU-Leverage Commands

### 7.1 Ollama — native install, GPU-resident models

```powershell
# Verify the driver sees the card before anything else
nvidia-smi

# Native Ollama install (not Docker) — lets it talk to the GPU driver directly
winget install Ollama.Ollama

# Set these as persistent environment variables (System Properties > Environment
# Variables, or via PowerShell as Administrator so they survive a restart):
setx OLLAMA_FLASH_ATTENTION 1
setx OLLAMA_KV_CACHE_TYPE q8_0
setx OLLAMA_KEEP_ALIVE 30m
setx OLLAMA_GPU_OVERHEAD 629145600
setx OLLAMA_MAX_LOADED_MODELS 2

# Restart the Ollama service/app after setting these, then pull both models
ollama pull phi4-mini
ollama pull nomic-embed-text

# Confirm both fit and the LLM is actually on GPU, not CPU
ollama ps
nvidia-smi
```

Notes on the values above:
- `OLLAMA_FLASH_ATTENTION=1` + `OLLAMA_KV_CACHE_TYPE=q8_0` shrink the KV cache further — not strictly required at this model size, but free to leave on since it just banks more headroom.
- `OLLAMA_GPU_OVERHEAD=629145600` reserves ~600MB as a safety margin so model loading doesn't OOM against display/driver overhead.
- `OLLAMA_KEEP_ALIVE=30m` keeps the model resident on GPU between requests instead of reloading it every call (reload is the slow part, not inference).
- `OLLAMA_MAX_LOADED_MODELS=2` lets `phi4-mini` (~2.5–3GB) and `nomic-embed-text` (~0.3GB) both stay loaded simultaneously — at ~3GB combined out of 6GB, you have real headroom left over, which is exactly what makes it comfortable for EasyOCR to also grab GPU memory on demand (Section 7.2) without the three fighting each other.

### 7.2 EasyOCR — GPU-accelerated OCR

```powershell
# Install the CUDA build of PyTorch matching your driver's CUDA version first —
# check your CUDA version with `nvidia-smi` (top-right of the output), then get
# the exact command for your version from https://pytorch.org/get-started/locally/
# Example for CUDA 12.1:
pip install torch --index-url https://download.pytorch.org/whl/cu121

# Then EasyOCR itself
pip install easyocr

# Sanity check it sees the GPU
python -c "import torch; print('CUDA available:', torch.cuda.is_available()); print(torch.cuda.get_device_name(0))"
```

In code, request the GPU explicitly rather than relying on auto-detection:

```python
import easyocr
reader = easyocr.Reader(['en'], gpu=True)
```

Keep the OCR call gated behind the native-extraction check from Section 2a — that's what keeps this from fighting Ollama for VRAM on every single document.

### 7.3 Qdrant — GPU indexing exists, but skip it here

Qdrant has supported GPU-accelerated HNSW indexing since v1.13 (a dedicated `qdrant/qdrant:*-gpu-nvidia` image, Linux-only). **Don't bother enabling it for this project**: GPU indexing pays off at large scale (millions of vectors, high-throughput bulk loads); at the scale of a single payer team's case documents, CPU indexing is already fast, and the GPU image would compete with Ollama for the same 6GB of VRAM for no real benefit. Keep Qdrant on the standard CPU image.

---

## 8. Decisions Log (this round)

| Item | Decision |
|---|---|
| LLM size | 3-4B class (`phi4-mini` primary, `llama3.2:3b` alt) — deliberate choice to keep GPU load light, not a hardware constraint. |
| Nurse lock timeout | 30 minutes of inactivity — confirmed. |
| Auth scope | All three roles (intake, nurse, admin) authenticate and are authorized; no unauthenticated routes anywhere. |
| Policy upload access | Admin-only. |
| Policy extraction failure | Manual add/edit/delete of requirement rows in the UI as a fallback — AI extraction is a draft, not final. |
| Case field auto-extraction | Best-effort per field; fields the model can't confidently find are left blank, never guessed. |
| Admin editing a decided case | Allowed, requires a mandatory comment, auto-routes the case back to nurse review tagged "Admin Edit"; original decision stays in the audit log. |
| Policy re-upload with same name | Overwrites (no versioning) — safe since only admins can upload. |
| Confidence bands | Present >= 85%, Absent < 70%, Unclear in between. |
| OCR provenance | Evidence sourced via OCR is visibly tagged "Extracted using OCR" in the nurse UI. |
| GPU leverage | Ollama (LLM + embeddings) and EasyOCR both run natively against the GPU wherever possible; Qdrant GPU indexing intentionally skipped (Section 7.3) as unnecessary overhead at this data scale. |
