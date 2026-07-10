# Compliance and Audit Checklist: pa-evidence-assistant

**Purpose**: Validate specification completeness and quality regarding data locality, human-in-the-loop rules, retrieval, and audit trails.
**Created**: 2026-07-10
**Feature**: [spec.md](../spec.md)

## Requirement Completeness

- [x] CHK001 - Are requirements explicitly stated to prohibit any public API calls for RAG/inference using document content? [Completeness, Spec §SEC-002] — Resolved: `security-compliance.md` §Data Locality Guarantees; `constitution.md` §II.
- [x] CHK002 - Is it explicitly documented that no path from intake to Accepted/Rejected can bypass an explicit human decision? [Completeness, Spec §SEC-001] — Resolved: `data-model.md` `review_status` enum has no automated terminal state; `constitution.md` §I.
- [x] CHK003 - Are logging requirements defined for every automated agent action and manual human decision? [Completeness, Spec §SEC-005] — Resolved: `security-compliance.md` §Audit Logging Requirements; `data-model.md` `AuditLog.action_type` enum (updated to resolve CHK009).

## Requirement Clarity

- [x] CHK004 - Is the "human-in-the-loop" decision requirement quantified by specifying exact roles (e.g., nurse, medical director)? [Clarity, Ambiguity] — Resolved: `ui-spec.md` Nurse Review Workspace names Nurse Reviewer / Medical Director explicitly; `data-model.md` `assigned_queue` includes `medical_director_review`.
- [x] CHK005 - Are exact-match identifier types (e.g., member ID, CPT codes) explicitly listed as requiring keyword/sparse search coverage? [Clarity, Spec §SEC-003] — Resolved: `rag-pipeline.md` §Exact-Match Identifier Coverage; `spec.md` FR-013, updated SEC-003.
- [x] CHK006 - Is the boundary for "local/on-prem" clearly defined in terms of network egress limits? [Clarity, Spec §SC-003] — Resolved: `cicd-deployment.md` §Automated Security & Compliance Gates names specific blocked hostnames and the AST enforcement mechanism.

## Coverage & Edge Cases

- [x] CHK007 - Are requirements defined for how the system behaves if a dense semantic search finds a match but the keyword search fails for an exact identifier? [Coverage, Edge Case] — Resolved: `rag-pipeline.md` §Dense-Hit / Keyword-Miss Handling; `spec.md` FR-013; `agent-spec.md` Retrieval and Reasoning Agent guardrails.
- [x] CHK008 - Are fallback requirements defined if the local inference environment becomes unavailable? [Coverage, Exception Flow] — Resolved: `spec.md` FR-014; `agent-spec.md` Retrieval/Reasoning Agent escalation paths (queued/retry + admin alert, no external fallback).
- [x] CHK009 - Are audit-trail requirements specified for scenarios where a human overrides a system recommendation? [Coverage, Exception Flow] — Resolved: `data-model.md` `CompletenessReportItem.overridden_status/overridden_by_id/overridden_at` fields and `AuditLog.action_type` includes `checklist_override` with required `details` fields.
- [x] CHK010 - Is there a requirement ensuring the system does not use hidden booleans for routing bypasses? [Coverage, Spec §SEC-001] — Resolved: `spec.md` SEC-001; `data-model.md` Case entity uses explicit enums only, confirmed by Phase 2 unit tests (`test_phase2_models.py`).
