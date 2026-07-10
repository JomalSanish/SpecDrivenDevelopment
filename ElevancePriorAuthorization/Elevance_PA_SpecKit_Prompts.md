# Elevance Prior Authorization Evidence Assistant — Spec-Kit Prompt Pack

This is a ready-to-paste prompt pack for building the app with GitHub Spec-Kit, following the
current official workflow order:

```
/speckit.constitution → /speckit.specify → /speckit.clarify → /speckit.checklist →
/speckit.plan → /speckit.tasks → /speckit.analyze → /speckit.implement
```

Run each command in your coding agent (Claude Code, Copilot, etc.) in this order. Don't skip
`/speckit.clarify`, `/speckit.checklist`, or `/speckit.analyze` — this project has enough
regulatory/confidentiality surface area that the quality gates matter.

## 0. Project setup

```bash
uv tool install specify-cli --from git+https://github.com/github/spec-kit.git
specify init elevance-pa-assistant --integration claude
cd elevance-pa-assistant
```

(Swap `claude` for your agent's integration key — `copilot`, `gemini`, `cursor-agent`, etc. If
your environment has no internet access at all, use Spec-Kit's air-gapped installation path with a
locally built wheel instead of the `git+https` install above.)

---

## 1. `/speckit.constitution`

Paste as-is. This sets the non-negotiable rules every later phase is checked against.

```
Elevance Prior Authorization Evidence Assistant — non-negotiable principles:

1. Human-in-the-loop only. No agent, workflow, or schema may represent, imply, or default to
an automated approve/deny/accept/reject outcome for a prior authorization case. Every case must
reach an explicit, attributed, timestamped decision made by a nurse reviewer or medical director
before it is marked Accepted or Rejected. Never model routing as a hidden boolean (e.g. a
`human_review_required` flag) — use explicit state fields instead (`review_status`,
`assigned_queue`, `decided_by`, `decision_at`).

2. Confidentiality and data locality, no exceptions. All uploaded material (payer policy
documents, provider clinical notes, benefit plan documents, member case attachments) is
confidential. No document content, embedding, or derived text may be sent to any public or
third-party hosted API — no OpenAI, no Anthropic, no cloud embedding/completion endpoints — for
any reason, including retrieval, summarization, or classification. All inference (embeddings,
reranking, LLM generation) runs on locally hosted / on-prem or private-VPC infrastructure with no
external egress for document content. Development and test environments use synthetic data only;
real PHI never appears outside production.

3. Hybrid retrieval is mandatory. Every retrieval path over policy or case documents must
combine dense semantic search with sparse/keyword search (BM25 or equivalent) so exact identifiers
(member ID, CPT/HCPCS, ICD-10 codes, document titles/section numbers) are never lost to
embedding-only matching.

4. Grounded, cited, fully auditable. Every evidence claim the system surfaces must carry a
citation to a specific source document and location, linked by a stable UUID — never an
unsupported claim. Every agent action, retrieval, model call, routing decision, and human decision
is logged with prompt, model/version, confidence score, and actor identity, sufficient to
reconstruct full case history for compliance audit.

5. Secrets management abstraction from day one. All credentials, connection strings, and API
keys go through a secrets-manager abstraction layer starting in the very first implementation
phase. This is never retrofitted later.

6. Five-agent runtime architecture, coordinated over a shared case state: Intake &
Classification, Evidence Retrieval (RAG), Policy Reasoning & Gap Analysis, Reviewer Summary &
Communication, Workflow/Audit & Deployment Readiness.

7. Spec-Driven Development discipline. Every phase produces the full specification set
(requirements, architecture, data, API, agent, RAG pipeline, UI, test, security & compliance,
CI/CD & deployment) before implementation begins. Run /speckit.analyze after every implementation
phase, not just once at the end.
```

---

## 2. `/speckit.specify`

Focus on *what* and *why* — no tech stack here, that comes in `/speckit.plan`.

```
Build the Elevance Prior Authorization Evidence Assistant: a payer-side web application that
helps payer operations teams process prior authorization (PA) requests from healthcare providers,
without the system itself ever making a clinical accept/reject decision.

Problem: Payers receive PA requests bundled with member demographics, provider clinical notes,
diagnosis/procedure codes, policy references, benefit rules, and supporting attachments (PDFs,
faxes, scans, referral forms). Reviewers must manually check whether every document required by
policy is present, whether the evidence supports the request, and whether the case should go to
nurse review, medical director review, or back to the provider for more documentation. Today this
is slow and error-prone.

Target users: Prior Authorization Intake Associate, Nurse Reviewer, Medical Director, Provider
Relations User, Operations Manager, Compliance/Audit User.

Core workflow:

1. Admin policy ingestion — An admin/compliance user uploads the governing policy document(s)
for a given procedure or service line (e.g. "MRI Lumbar Spine criteria"). The system parses this
policy document and extracts the definitive list of required supporting documents/evidence types
for that policy (e.g. clinical notes, conservative therapy records of at least 6 weeks, imaging
necessity justification).

2. Case submission — A provider or intake associate uploads the case documents for a specific PA
request (clinical notes, prior therapy records, imaging orders, referral forms, etc.) along with
case metadata: member ID, provider ID, CPT/HCPCS code, ICD-10 code, service type, requested date.

3. Automated completeness verification — for the policy tied to this case, the system determines
whether each required document/evidence type from step 1 is present among the documents uploaded
in step 2. This check must run over a locally hosted, hybrid (dense + keyword) retrieval pipeline
— case and policy documents are confidential and must never touch a public or third-party API.
Output is a checklist: each required item marked Present / Absent / Unclear, with a citation to
the matching case document when present, and a confidence score.

4. Routing to Nurse Review — once the automated completeness check finishes, regardless of
outcome, the case is routed into a distinct Nurse Review section of the app. The system never
auto-approves or auto-rejects based on the completeness check alone.

5. Nurse manual review — in the Nurse Review section, the nurse sees the case summary, the full
list of uploaded documents, the system's completeness checklist with citations, and the
underlying documents themselves (viewable in-app). The nurse can independently open and inspect
every document, optionally annotate or override the system's completeness assessment, and then
record an explicit decision: Accept (evidence sufficient — case proceeds to the next step, e.g.
medical director review or standard processing) or Reject (case sent back to the provider with a
specific missing-documentation request). This decision is always a manual, attributed, timestamped
human action — never automated.

6. Every step — policy ingestion, completeness check, routing, nurse decision — is fully logged
for audit: which documents were checked, which retrieval method matched them, confidence scores,
and who made the human decision and when.

Functional requirements: case ingestion; document upload/parsing with an OCR placeholder; policy
document ingestion and requirement extraction; hybrid local RAG retrieval; multi-agent
orchestration across the 5 agents (Intake & Classification, Evidence Retrieval/RAG, Policy
Reasoning & Gap, Reviewer Summary & Communication, Workflow/Audit & Deployment Readiness); case
summarization; missing-document detection; policy evidence mapping; a Nurse Review dashboard with
document viewer and Accept/Reject action; an audit log; reviewer checklist generation;
provider-facing missing-document communication drafts.

Out of scope: automated approval or denial of any kind; final clinical decisioning by the system;
real payer system integration (mocked only); real PHI in development; claims/payment adjudication;
regulatory/legal determination.

Sample interactions to account for: "Create a new PA case", "What information is missing in this
case?", "What evidence supports this request?", "Do we have enough evidence for review?", "What
documents are missing?", "Summarize the case for review", "Which queue should this case go to?",
"Show the audit trail for this case", "Which sources were used to generate this summary?", "What
happens if no evidence is found?", "What if contradictory data is found?"
```

---

## 3. `/speckit.clarify`

Run once with no arguments to get the full interactive pass, or seed it with the areas most
likely to be ambiguous for this project:

```
Focus clarification on:
1. The exact confidence-threshold rule for classifying a required document as Present vs. Absent
vs. Unclear.
2. What happens if a nurse takes no action on a case within SLA — escalation path and ownership.
3. Whether multiple nurses can be assigned to, or claim, the same case concurrently.
4. How a policy document update/version change propagates to cases already in flight against the
old version.
5. Supported document formats and the OCR fallback behavior for scanned/faxed documents.
6. Required fields for the Accept and Reject actions — does Reject require a structured reason
code in addition to free-text notes, and is Accept reversible?
```

---

## 4. `/speckit.checklist`

```
Generate a requirements-quality checklist focused on:
- Confidentiality / data-locality guarantees — confirm no requirement implies or permits a call
to a public API for document content anywhere in the retrieval or generation path.
- The human-in-the-loop guarantee — confirm no path from intake to Accepted/Rejected can bypass
an explicit nurse or medical director decision.
- Hybrid retrieval coverage — confirm exact-match identifiers (member ID, codes, document titles)
are covered by keyword/sparse search, not dense search alone.
- Audit-trail completeness — confirm every agent action and every human decision has a defined
log entry.
```

---

## 5. `/speckit.plan`

This is where the tech stack, the local hybrid-RAG design, and the non-default artifacts get
specified. Adjust the base stack line to whatever your team has standardized on; the RAG/security
requirements below should stay as-is.

```
Backend: Python (FastAPI). Frontend: React. Primary datastore: PostgreSQL for case/workflow state.
Object storage: local/on-prem (e.g. MinIO) for uploaded documents.

RAG and retrieval layer — must run entirely on-prem / locally hosted, zero public API calls:
- Vector store: self-hosted Qdrant (or OpenSearch if the team already runs an ELK stack), using
native hybrid search so dense and sparse vectors are queried together.
- Embeddings: a locally served open-weight embedding model (e.g. BAAI/bge-large-en-v1.5 or
intfloat/e5-large-v2) behind an internal inference service (e.g. Text Embeddings Inference or
sentence-transformers wrapped in FastAPI) — never a hosted embeddings API.
- Sparse retrieval: BM25 run alongside dense retrieval (via Qdrant's sparse vectors or a dedicated
OpenSearch index), fused with reciprocal rank fusion or a weighted hybrid score.
- LLM generation/reasoning: a locally hosted open-weight model served via vLLM or Ollama behind an
internal OpenAI-compatible endpoint that never leaves the private network — no calls to any public
LLM API for document-derived content.
- Optional but preferred: a local cross-encoder reranker over the fused hybrid candidates before
handing results to the Policy Reasoning & Gap Agent.

Document completeness verification pipeline:
- Admin policy ingestion parses the uploaded policy document per service line into a structured
`policy_requirement_checklist`: a list of required evidence/document types, each with an id,
description, and matching criteria.
- Case documents are chunked and hybrid-indexed into an isolated, case-scoped collection — never
mixed across cases.
- For each item in `policy_requirement_checklist`, run hybrid retrieval scoped to that case's
document collection; classify the item as Present (with matching document id, chunk id, and
confidence score), Absent, or Unclear (ambiguous match below a configurable confidence threshold).
- Persist the full per-item result as a `completeness_report` — never collapse it to a single
pass/fail boolean.

Nurse Review workflow:
- Regardless of `completeness_report` outcome, route the case into a distinct Nurse Review
queue/section once the automated check completes.
- Nurse Review UI shows: case summary, full `completeness_report` with citations, an in-app
document viewer for every uploaded case document, and two explicit actions — Accept and Reject —
each requiring the nurse's identity, a timestamp, and (for Reject) a structured reason plus
free-text note that can seed a provider-facing message draft.
- The nurse's decision is its own auditable record, separate from and never overwriting the
automated `completeness_report`.

Data model constraints:
- No boolean field may imply an automated decision (do not use anything like
`human_review_required: true/false`). Use an explicit `review_status` enum (e.g.
`pending_verification`, `in_nurse_review`, `accepted`, `rejected`, `returned_to_provider`) plus
`decided_by`, `decided_at`, `decision_reason`.
- Every case, document, chunk, and citation gets a UUID so evidence always traces to an exact
source location.

Security and secrets:
- All credentials/connection strings for the vector store, embedding server, LLM server, and
object storage go through a secrets-manager abstraction (e.g. HashiCorp Vault, or your cloud KMS
wrapped behind an internal interface) starting in Phase 1 — not hardcoded, not retrofitted later.

Generate these additional specification artifacts alongside the default plan.md, research.md,
data-model.md, contracts/, and quickstart.md:
- agent-spec.md — detailed spec for each of the 5 agents: inputs, outputs, tools, guardrails,
escalation rules.
- rag-pipeline.md — the hybrid retrieval pipeline, chunking strategy, index refresh strategy, and
confidence thresholds for Present/Absent/Unclear.
- ui-spec.md — screens for Intake, the Operations dashboard, and the Nurse Review section
(document viewer + Accept/Reject).
- security-compliance.md — data-locality guarantees, no-public-API enforcement (including how CI
verifies no external egress), audit logging requirements, and the PHI handling policy for
dev/test.
- cicd-deployment.md — deployment pipeline including an automated check that fails the build if
any code path calls a public LLM/embedding API endpoint.
```

---

## 6. `/speckit.tasks`

```
Break the plan into phased, dependency-ordered tasks, grouped as:
Phase 1: Foundation, secrets-manager abstraction, local embedding/LLM serving stubs.
Phase 2: Document ingestion, policy parsing, requirement-checklist extraction.
Phase 3: Hybrid RAG indexing and retrieval (dense + sparse + fusion).
Phase 4: Completeness verification pipeline (Present/Absent/Unclear classification).
Phase 5: Nurse Review UI — document viewer, completeness report display, Accept/Reject actions.
Phase 6: Multi-agent orchestration and audit logging across all 5 agents.
Phase 7: Automated tests derived from specs.
Phase 8: CI/CD, encryption/TLS hardening, deployment readiness checks.

Flag, rather than silently complete, any task that would require external network access or a
call to a public API.
```

---

## 7. `/speckit.analyze`

```
Cross-check spec.md, plan.md, and tasks.md for consistency before implementation. Specifically
re-verify:
(a) no schema anywhere includes an automated-decision boolean (e.g. a `human_review_required`-
style field) — routing must stay explicit and queue-based;
(b) every RAG/LLM call path stays inside the local/private network with no public-API dependency;
(c) every artifact requested in the plan (agent-spec.md, rag-pipeline.md, ui-spec.md,
security-compliance.md, cicd-deployment.md) exists and is consistent with tasks.md.
```

Re-run `/speckit.analyze` after each implementation phase completes — not only once before
`/speckit.implement` — so drift gets caught while the plan and tasks can still be adjusted.

---

## 8. `/speckit.implement`

```
Implement Phase 1 only. Validate it works (secrets abstraction is wired, local embedding and LLM
endpoints are reachable, no external calls occur) before moving to the next phase.
```

Repeat per phase (`Implement Phase 2`, `Implement Phase 3`, …), running `/speckit.analyze` between
phases. This keeps the agent's context from saturating on a large task list and gives you a
checkpoint to catch scope or confidentiality drift early, which is cheaper than fixing it after
Phase 4 or later.

---

## Notes

- **Before `/speckit.plan` runs**, have your local embedding server, vector store, and LLM
inference endpoint actually deployed and reachable — the agent will wire configuration against
them, and a plan built against endpoints that don't exist yet tends to drift once implementation
starts.
- **CI egress check**: worth adding a simple CI step early (Phase 1 or Phase 8) that fails the
build if it detects an outbound call to a public LLM/embedding host — this is cheap to add early
and expensive to retrofit.
- If your installed Spec-Kit version supports a post-implementation gap-sweep command (some
recent releases add one), run it after Phase 8 to catch any task the agent under-built, then
re-run `/speckit.implement` until it reports the feature complete.
