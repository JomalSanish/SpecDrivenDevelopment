<!--
Sync Impact Report:
- Version change: 0.0.0 -> 1.0.0
- List of modified principles:
  - Initialized with Principles 1-7
- Added sections:
  - Human-in-the-loop Only
  - Confidentiality and Data Locality
  - Hybrid Retrieval
  - Grounded, Cited, Fully Auditable
  - Secrets Management Abstraction
  - Five-Agent Runtime Architecture
  - Spec-Driven Development Discipline
- Removed sections: N/A
- Templates requiring updates:
  - ✅ .specify/templates/plan-template.md
  - ✅ .specify/templates/spec-template.md
  - ✅ .specify/templates/tasks-template.md
- Deferred items: None
-->

# Elevance Prior Authorization Evidence Assistant Constitution

## Core Principles

### I. Human-in-the-loop Only
No agent, workflow, or schema may represent, imply, or default to an automated approve/deny/accept/reject outcome for a prior authorization case. Every case must reach an explicit, attributed, timestamped decision made by a nurse reviewer or medical director before it is marked Accepted or Rejected. Never model routing as a hidden boolean (e.g. a `human_review_required` flag) — use explicit state fields instead (`review_status`, `assigned_queue`, `decided_by`, `decision_at`).

### II. Confidentiality and Data Locality
All uploaded material (payer policy documents, provider clinical notes, benefit plan documents, member case attachments) is confidential. No document content, embedding, or derived text may be sent to any public or third-party hosted API — no OpenAI, no Anthropic, no cloud embedding/completion endpoints — for any reason, including retrieval, summarization, or classification. All inference (embeddings, reranking, LLM generation) runs on locally hosted / on-prem or private-VPC infrastructure with no external egress for document content. Development and test environments use synthetic data only; real PHI never appears outside production.

### III. Hybrid Retrieval
Hybrid retrieval is mandatory. Every retrieval path over policy or case documents must combine dense semantic search with sparse/keyword search (BM25 or equivalent) so exact identifiers (member ID, CPT/HCPCS, ICD-10 codes, document titles/section numbers) are never lost to embedding-only matching.

### IV. Grounded, Cited, Fully Auditable
Every evidence claim the system surfaces must carry a citation to a specific source document and location, linked by a stable UUID — never an unsupported claim. Every agent action, retrieval, model call, routing decision, and human decision is logged with prompt, model/version, confidence score, and actor identity, sufficient to reconstruct full case history for compliance audit.

### V. Secrets Management Abstraction
All credentials, connection strings, and API keys go through a secrets-manager abstraction layer starting in the very first implementation phase. This is never retrofitted later.

### VI. Five-Agent Runtime Architecture
The system employs a five-agent runtime architecture coordinated over a shared case state:
- Intake & Classification
- Evidence Retrieval (RAG)
- Policy Reasoning & Gap Analysis
- Reviewer Summary & Communication
- Workflow/Audit & Deployment Readiness

### VII. Spec-Driven Development Discipline
Every phase produces the full specification set (requirements, architecture, data, API, agent, RAG pipeline, UI, test, security & compliance, CI/CD & deployment) before implementation begins. Run `/speckit.analyze` after every implementation phase, not just once at the end.

## Governance

Amendments to this constitution require documentation, approval, and a migration plan. The Constitution supersedes all other practices and policies. All pull requests and code reviews MUST verify compliance with these core principles. Any deviation requires formal review and exception logging.

**Version**: 1.0.0 | **Ratified**: 2026-07-10 | **Last Amended**: 2026-07-10
