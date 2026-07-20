<!--
SYNC IMPACT REPORT
==================
Version change: [TEMPLATE] → 1.0.0  (initial ratification)
Modified principles: n/a (initial fill-in from blank template)
Added sections:
  - I. On-Premises Inference Only
  - II. Human-Only Clinical Routing
  - III. Authentication & Authorization Everywhere
  - IV. LLM Sizing & Reliability
  - V. Hybrid Document Extraction (Native + OCR)
  - VI. Best-Effort Field Extraction
  - VII. Completeness Confidence Bands
  - VIII. Hybrid Retrieval Strategy
  - IX. Policy Management
  - X. Case Editing & Audit Trail
  - XI. Nurse Case Locking
  - XII. Infrastructure Ceiling
  - XIII. Secrets Abstraction
  - XIV. Schema Change Discipline
  - Security & Compliance Constraints
  - Development Workflow
  - Governance
Removed sections: none
Templates updated:
  ✅ .specify/templates/plan-template.md — Constitution Check section updated
  ✅ .specify/templates/spec-template.md — added mandatory constraint alignment notes
  ✅ .specify/templates/tasks-template.md — added constitution-driven task categories
Follow-up TODOs:
  - TODO(RATIFICATION_DATE): Confirm exact project ratification date with team lead.
    Using project-start estimate 2026-07-20.
-->

# Elevance PA Evidence Assistant (v2) Constitution

## Core Principles

### I. On-Premises Inference Only

All LLM inference, embedding generation, OCR, and persistent storage MUST run
on-premises on the designated single Windows host (RTX 3050, 6 GB VRAM, 12th-gen
i5, 16 GB RAM). No feature, task, or configuration may introduce a call to any
external AI/ML API (OpenAI, Anthropic, Azure AI, Google AI, Hugging Face
Inference API, etc.) or any external storage endpoint (S3, GCS, Azure Blob, etc.).

**Rationale**: Regulatory and privacy requirements mandate that PHI and clinical
documents never leave the organizational perimeter.

---

### II. Human-Only Clinical Routing

Every case submission MUST route unconditionally to the nurse review queue.
There is no automated approval, automated denial, or probability-based bypass.
The schema MUST NOT contain a `human_review_required` field or any boolean that
gates human review — routing to a human is the only path. A nurse's
"accept" / "reject" action is a documentation-completeness and routing decision,
not a clinical approval or denial.

**Rationale**: Clinical decisions carry liability and regulatory accountability
that cannot be delegated to an automated system.

---

### III. Authentication & Authorization Everywhere

Every application route — without exception — MUST require a valid JWT issued by
the internal OAuth2 password-grant endpoint, and MUST perform an explicit role
check (intake / nurse / admin) before executing any business logic. There are no
public or unauthenticated routes, and no route that accepts a token without
verifying the role.

**Rationale**: PHI access must be fully traceable to an authenticated, authorized
individual at all times.

---

### IV. LLM Sizing & Reliability

The production LLM MUST be a 3–4 B parameter class model (phi4-mini or
llama3.2:3b are the approved choices). Configuration MUST be tuned to maximize
structured JSON output reliability and guaranteed completion over raw accuracy.
Larger or slower models MUST NOT be introduced without a written amendment to
this constitution, even as a temporary workaround.

**Rationale**: The host GPU (RTX 3050, 6 GB VRAM) cannot sustain larger models
alongside concurrent embedding and OCR workloads without degrading user-facing
latency to unacceptable levels. Reliable JSON output is more valuable than
marginal accuracy gains.

---

### V. Hybrid Document Extraction (Native + OCR)

Text extraction from any document (case or policy) MUST attempt native PDF text
extraction (PyMuPDF) first on every page. OCR (EasyOCR, GPU-accelerated) MUST
only be invoked for pages where native extraction returns near-empty text. Every
text chunk stored in the retrieval index MUST carry metadata indicating whether
its source text came from native extraction or OCR. The nurse-facing UI MUST
display a visible indicator (e.g., a labeled badge) on any evidence surfaced from
an OCR-sourced chunk.

**Rationale**: Native extraction is faster and more accurate; OCR is reserved
for scanned/faxed pages. Provenance labeling enables nurses to calibrate trust
in extracted evidence.

---

### VI. Best-Effort Field Extraction

Case field auto-extraction is strictly best-effort. The LLM MUST populate only
the fields it can identify with confidence from the uploaded documents. Fields
the model cannot confidently locate MUST be left blank for manual nurse/intake
entry. The system MUST NOT fabricate or guess field values.

**Rationale**: A blank field prompts a human to fill it correctly; a wrong
pre-filled value may be trusted and propagate an error into the record.

---

### VII. Completeness Confidence Bands

Requirement-match confidence scores MUST be binned into exactly three bands:
- **Present**: score ≥ 85%
- **Unclear**: 70% ≤ score < 85%
- **Absent**: score < 70%

No feature may introduce finer-grained or floating-point confidence displays to
end users. Band boundaries MUST NOT be changed without a MAJOR version amendment.

**Rationale**: Clinical end-users benefit from clear, actionable categories
rather than raw probability scores, which can be misleading and invite
inconsistent interpretation.

---

### VIII. Hybrid Retrieval Strategy

Retrieval MUST apply the following logic, with no shortcuts:

1. **Structured identifiers** (case ID, member ID, policy name, CPT/HCPCS,
   ICD-10): resolve via exact/keyword match against indexed PostgreSQL columns
   first; fall back to Qdrant sparse/BM25 only when the identifier appears
   solely in free-text content.
2. **Clinical narrative requirements**: resolve via semantic dense vector search
   against Qdrant.
3. **Mixed requirements**: combine keyword and semantic scores via Reciprocal
   Rank Fusion (RRF). A semantically confident chunk with zero keyword
   corroboration on an identifier-bearing requirement MUST produce an "Unclear"
   status (keyword-miss cap), never "Present".

**Rationale**: Pure semantic search mis-identifies structurally distinct
identifiers; pure keyword search misses paraphrased clinical evidence.
The keyword-miss cap prevents false-positive "Present" verdicts on identifier
fields.

---

### IX. Policy Management

Policy upload MUST be restricted to admin-only. AI-assisted extraction of policy
requirements into a checklist MUST support full manual add, edit, and delete of
individual requirement rows by the admin before saving. Re-uploading a policy
with an existing name MUST overwrite the previous version without creating a
version history — this is acceptable because only admins can upload policies.

**Rationale**: Policy documents change over time; admins need a simple,
authoritative single-version record rather than a version history that could
cause confusion about which version governs a case.

---

### X. Case Editing & Audit Trail

Admin users MAY edit any case regardless of its review status. Editing a case
that already has a nurse decision MUST require the admin to provide a mandatory
comment, and MUST automatically re-route the case into the nurse review queue
tagged "Admin Edit" with the admin's name and comment. The original decision
MUST be preserved in the audit log; it MUST NOT be overwritten or deleted.

**Rationale**: Providing a correction path while preserving the original decision
satisfies both usability and regulatory auditability requirements.

---

### XI. Nurse Case Locking

A nurse who opens a case MUST hold an exclusive lock on that case. The lock MUST
auto-release after 30 minutes of inactivity. No other nurse may edit a
concurrently locked case.

**Rationale**: Prevents concurrent edits and conflicting nurse decisions on the
same case.

---

### XII. Infrastructure Ceiling

At most two always-on Docker containers are permitted: one for PostgreSQL, one for
Qdrant. The LLM, the embedding model, and GPU-accelerated OCR MUST run as
natively-installed (non-containerized) processes on the host OS so they can
access the NVIDIA GPU directly. Docker/WSL2 GPU passthrough is explicitly
prohibited for these workloads.

**Rationale**: The RTX 3050 with 6 GB VRAM cannot sustain NVIDIA GPU passthrough
overhead alongside production inference load. Containerizing the GPU workloads
would violate Principle I (latency) and Principle IV (reliability).

---

### XIII. Secrets Abstraction

All secrets (DB credentials, JWT signing keys, model paths, API tokens for
internal services) MUST be accessed exclusively through a single secrets-
abstraction module. Direct calls to `os.environ`, `dotenv`, or any other
environment-access mechanism outside that module are prohibited throughout the
codebase.

**Rationale**: A single choke point enables rotation, auditing, and environment-
specific secret backends without touching application code.

---

### XIV. Schema Change Discipline

Every database schema change MUST ship as an Alembic migration file. Migrations
that have already been applied to any environment MUST NOT be edited. New
changes require new migration files.

**Rationale**: Editing applied migrations breaks reproducibility of the schema
history and can cause silent data-integrity failures in environments that have
already run the original migration.

---

## Security & Compliance Constraints

- All routes enforce JWT validation + role check (see Principle III).
- PHI never leaves the on-premises network (see Principle I).
- All case mutations (create, update, admin-edit, nurse decision) MUST write an
  immutable audit-log entry recording: actor identity, role, timestamp, action
  type, and a before/after snapshot of changed fields.
- Secrets MUST NOT appear in source code, git history, logs, or error messages
  (see Principle XIII).
- Nurse case locks MUST prevent concurrent edits (see Principle XI).
- Automated clinical decisions are unconditionally prohibited (see Principle II).

## Development Workflow

- Every new feature starts with a spec (`/speckit-specify`), then a plan
  (`/speckit-plan`), then tasks (`/speckit-tasks`), then implementation
  (`/speckit-implement`).
- The Constitution Check in `plan-template.md` MUST be completed and all
  violations justified before Phase 0 research begins.
- Every schema change ships with an Alembic migration (Principle XIV).
- Secrets MUST be routed through the secrets-abstraction module from day one;
  no temporary `os.environ` calls (Principle XIII).
- GPU workloads (LLM, embeddings, OCR) MUST be tested on the designated host
  hardware before any feature that touches them is marked complete.
- Clinical routing logic MUST be reviewed by a domain lead to confirm no
  automated decision path has been introduced (Principle II).

## Governance

This constitution supersedes all other project guidelines, team agreements, and
prior implementation plans. In case of conflict between any other document and
this constitution, this constitution governs.

**Amendment procedure**:
1. Propose the amendment as a pull request modifying this file.
2. Obtain sign-off from the project lead and, for Principles II and III, also
   from the compliance representative.
3. Run `/speckit-constitution` after approval to propagate changes to all
   dependent templates.
4. Tag the commit with the new version (e.g., `constitution-v1.1.0`).

**Versioning policy** (Semantic Versioning):
- MAJOR: Removal or redefinition of an existing principle.
- MINOR: New principle or materially expanded guidance added.
- PATCH: Clarifications, wording, or non-semantic refinements.

**Compliance review**: At minimum before each production release, a designated
reviewer MUST verify that no change in any merged PR violates Principles II, III,
or VIII. Findings MUST be logged in the audit trail.

---

**Version**: 1.0.0 | **Ratified**: 2026-07-20 | **Last Amended**: 2026-07-20
