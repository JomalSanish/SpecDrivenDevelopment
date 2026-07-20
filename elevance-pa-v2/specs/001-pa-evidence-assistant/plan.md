# Implementation Plan: Elevance Prior Authorization Evidence Assistant (v2)

**Branch**: `001-pa-evidence-assistant` | **Date**: 2026-07-20 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/001-pa-evidence-assistant/spec.md`

## Summary

Build a payer-side, fully on-premises Prior Authorization Evidence Assistant that routes every case unconditionally to human nurse review. The system accepts PDF submissions from intake associates, extracts text via PyMuPDF (native) with EasyOCR GPU fallback, runs a 5-agent RAG pipeline (Intake Classification → Evidence Retrieval → Policy Reasoning → Reviewer Summary → Workflow/Audit) to generate a per-requirement completeness report, and surfaces that report to nurses alongside the original PDFs. Admins manage policies, staff accounts, and a searchable immutable audit log, and may re-open decided cases. The stack is Python/FastAPI backend + React/Vite/TypeScript frontend, two Docker services (PostgreSQL, Qdrant), and natively-installed Ollama (phi4-mini + nomic-embed-text) with EasyOCR, all running on the designated Windows host.

---

## Technical Context

**Language/Version**: Python 3.11 (backend) · Node 20 / TypeScript 5 (frontend)

**Primary Dependencies**:
- Backend: FastAPI 0.111+, SQLAlchemy 2.x (async, asyncpg), Alembic, python-jose, passlib[argon2], PyMuPDF (fitz), EasyOCR, httpx, qdrant-client 1.9+, pydantic-settings
- Frontend: React 18, Vite 5, TypeScript 5, Tailwind CSS 3, shadcn/ui, lucide-react, axios/fetch

**Storage**:
- PostgreSQL 16 (Docker) — cases, documents, policies, policy_requirements, completeness_report_items, case_status_history, users, refresh_tokens, audit_logs
- Qdrant (Docker) — `pa-evidence` collection: dense (768-dim, nomic-embed-text) + sparse (BM25) vectors, filtered by `case_id`
- Local filesystem (`/data/documents/{case_id}/{doc_id}.pdf`) behind `StorageService` abstraction

**Testing**: pytest + pytest-asyncio (backend) · Vitest (frontend unit) · manual integration via quickstart.md

**Target Platform**: Windows 11 host (single-box on-prem) · Chrome/Edge browser clients on LAN

**Performance Goals**:
- Case creation response: < 1s (async background pipeline)
- Pipeline completion: < 5 min per 3-document case (SC-003)
- Case creation end-to-end UX: < 3 min (SC-001)
- Lock heartbeat latency: < 200ms (LAN)
- Auth token endpoint: < 500ms p95

**Constraints**:
- GPU: RTX 3050, 6 GB VRAM — phi4-mini (~2.5–3 GB) + nomic-embed-text (~275 MB) + EasyOCR (~1 GB peak) must coexist without OOM
- RAM: 16 GB — PostgreSQL (~200 MB) + Qdrant (~200 MB) + FastAPI + browser on same box
- Docker containers: exactly 2 (postgres, qdrant) — Ollama and EasyOCR run natively
- Zero external API calls anywhere in the system

**Scale/Scope**: ~5–15 concurrent internal staff users; single payer org; single-site deployment; English only

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design — all gates remain ✅.*

| # | Principle | Gate Question | Status |
|---|-----------|---------------|--------|
| I | On-Premises Inference Only | Does this feature introduce any call to an external AI/ML or storage API? | ✅ Pass — all inference (Ollama), embeddings (nomic-embed-text via Ollama), OCR (EasyOCR), and storage (local FS + PostgreSQL + Qdrant) are on-prem. Zero external API calls. |
| II | Human-Only Clinical Routing | Does this feature add any automated approve/deny path, or introduce a `human_review_required` boolean? | ✅ Pass — there is no automated routing decision, no `human_review_required` field. Every case routes unconditionally to the nurse queue. Accept/Reject is a documentation-completeness routing decision only. |
| III | Auth & Authz Everywhere | Does every new route carry JWT validation AND an explicit role check? | ✅ Pass — every FastAPI route uses a `require_role([...])` dependency. No unauthenticated route exists. |
| IV | LLM Sizing & Reliability | If LLM is used, is the model ≤ 4 B params (phi4-mini or llama3.2:3b) with JSON-structured output? | ✅ Pass — phi4-mini (3.8B, Q4_K_M) in JSON mode for all extraction, reasoning, and summarization. |
| V | Hybrid Document Extraction | Does text extraction attempt native PDF (PyMuPDF) first, OCR (EasyOCR) only on near-empty pages, with chunk-level provenance metadata? | ✅ Pass — extraction_method ("native"\|"ocr") stored per chunk; EasyOCR only triggers on pages returning < threshold chars from PyMuPDF. |
| VI | Best-Effort Field Extraction | Does the LLM leave unconfident fields blank rather than guessing? | ✅ Pass — FR-013/FR-013a: only Member ID + Requested Service/Procedure are required; all other fields left null if not confidently found. |
| VII | Confidence Bands | Are confidence displays limited to the three bands (Present ≥85%, Unclear 70–85%, Absent <70%)? | ✅ Pass — FR-024: exactly three verdict statuses; no raw scores exposed to users. |
| VIII | Hybrid Retrieval | Does retrieval apply exact/keyword for identifiers and dense semantic for narrative, with RRF + keyword-miss cap? | ✅ Pass — identifier requirements → PostgreSQL indexed columns (or Qdrant BM25 sparse); narrative → Qdrant dense; mixed → RRF with keyword-miss cap forcing Unclear. |
| IX | Policy Management | Is policy upload restricted to admin? Does the UI support full manual add/edit/delete before save? | ✅ Pass — FR-040/FR-043: policy write routes gated to admin role; checklist presented as editable draft before save. |
| X | Case Editing & Audit Trail | Does admin-edit of a decided case require a comment, re-queue it, and preserve the original decision in the audit log? | ✅ Pass — FR-053/FR-054/FR-055: mandatory comment, automatic re-queue tagged "Admin Edit," original decision event immutable in audit_logs. |
| XI | Nurse Case Locking | Does opening a case acquire an exclusive lock with a 30-min inactivity auto-release? | ✅ Pass — FR-031/FR-032: exclusive lock on case open; heartbeat-based `last_active_at`; 30-min background expiry job. |
| XII | Infrastructure Ceiling | Does this feature require more than 2 Docker containers, or attempt to run GPU workloads inside Docker/WSL2? | ✅ Pass — docker-compose.yml defines exactly postgres + qdrant. Ollama and EasyOCR run natively on the Windows host GPU. |
| XIII | Secrets Abstraction | Are all secrets accessed through the secrets-abstraction module (no raw `os.environ` calls)? | ✅ Pass — `src/core/secrets.py` is the single secrets choke point. All config reads (DB URL, JWT key, Ollama endpoint, Qdrant host) go through it. |
| XIV | Schema Change Discipline | Are all schema changes shipped as new Alembic migrations (no edits to applied migrations)? | ✅ Pass — `alembic/` directory, one migration per schema change, no retroactive edits. |

---

## Project Structure

### Documentation (this feature)

```text
specs/001-pa-evidence-assistant/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── auth.md
│   ├── cases.md
│   ├── documents.md
│   ├── policies.md
│   ├── nurse-review.md
│   ├── admin.md
│   └── audit.md
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
backend/
├── src/
│   ├── core/
│   │   ├── config.py          # pydantic-settings; reads .env.local
│   │   ├── secrets.py         # Secrets abstraction (Principle XIII)
│   │   ├── database.py        # Async SQLAlchemy engine + session factory
│   │   ├── security.py        # JWT sign/verify, password hashing (argon2)
│   │   └── dependencies.py    # require_role(), get_current_user() FastAPI deps
│   ├── models/
│   │   ├── user.py            # User, RefreshToken
│   │   ├── case.py            # Case, CaseStatusHistory
│   │   ├── document.py        # Document, Chunk
│   │   ├── policy.py          # Policy, PolicyRequirement
│   │   ├── completeness.py    # CompletenessReportItem
│   │   └── audit.py           # AuditLog
│   ├── agents/
│   │   ├── intake_agent.py         # Agent 1: case field extraction + policy requirement extraction
│   │   ├── retrieval_agent.py      # Agent 2: dense + sparse Qdrant search
│   │   ├── reasoning_agent.py      # Agent 3: policy gap analysis → Present/Absent/Unclear
│   │   ├── summary_agent.py        # Agent 4: nurse-facing case narrative summary
│   │   └── workflow_agent.py       # Agent 5: routing, lock management, health checks
│   ├── services/
│   │   ├── storage_service.py      # StorageService abstraction (local FS impl)
│   │   ├── extraction_service.py   # PyMuPDF native + EasyOCR GPU fallback
│   │   ├── chunking_service.py     # Sentence-based chunker, 512-token / 50-token overlap
│   │   ├── embedding_service.py    # nomic-embed-text via Ollama /api/embeddings
│   │   ├── qdrant_service.py       # Index + search pa-evidence collection
│   │   ├── fusion_service.py       # RRF fusion + keyword-miss cap
│   │   ├── lock_service.py         # Nurse case lock acquire/release/heartbeat
│   │   ├── sla_service.py          # Background SLA escalation loop (48h default)
│   │   └── audit_service.py        # Immutable audit log writer
│   ├── pipelines/
│   │   └── completeness_pipeline.py  # Orchestrates agents 1-4 as background task
│   └── api/
│       ├── auth.py            # POST /api/v1/auth/token, /refresh, /logout
│       ├── cases.py           # Case CRUD + status polling (intake role)
│       ├── documents.py       # PDF upload + streaming serve
│       ├── policies.py        # Policy CRUD + requirement checklist
│       ├── nurse_review.py    # Queue, lock/heartbeat/unlock, accept/reject
│       ├── admin.py           # All-cases, user management, admin case edit
│       └── audit.py           # Audit log search/browse
├── alembic/
│   ├── env.py
│   └── versions/              # One file per schema change — never edit applied
├── tests/
│   ├── unit/
│   ├── integration/
│   └── contract/
├── main.py                    # FastAPI app entry point, lifespan, router registration
├── docker-compose.yml         # postgres + qdrant ONLY
└── .env.local                 # Local secrets (gitignored)

frontend/
├── src/
│   ├── components/
│   │   ├── layout/            # Sidebar, TopBar, RoleGate
│   │   ├── cases/             # CaseList, NewCaseForm, CaseStatusBadge, PollingWrapper
│   │   ├── nurse/             # Queue, CaseDetailView, RAGSummary, DocumentViewer, VerdictBadge
│   │   ├── policy/            # PolicyList, PolicyDetail, RequirementEditor
│   │   ├── admin/             # AllCasesTable, UserManagement, AuditLogViewer
│   │   └── shared/            # OcrTag, ConfidenceBadge, AdminEditBanner, LoadingSpinner
│   ├── pages/
│   │   ├── LoginPage.tsx
│   │   ├── CaseManagementPage.tsx
│   │   ├── NurseReviewPage.tsx
│   │   ├── PolicyManagementPage.tsx
│   │   └── AdminPage.tsx
│   ├── services/
│   │   └── api.ts             # All fetch calls, auth headers, token refresh interceptor
│   ├── hooks/
│   │   ├── usePolling.ts      # Generic polling hook (5-10s interval, stops on terminal status)
│   │   └── useLockHeartbeat.ts # Sends /cases/{id}/heartbeat every 2 min while case is open
│   └── stores/
│       └── authStore.ts       # JWT/role state (zustand or context)
├── index.html
└── vite.config.ts
```

**Structure Decision**: Web application layout (backend/ + frontend/) with backend following v1 module boundaries (core, models, agents, services, api) and adding `pipelines/` as an explicit layer for the completeness orchestrator. Frontend uses page-per-sidebar-section with shared component library.

---

## Complexity Tracking

> All 14 constitution gates pass. No violations to justify.
