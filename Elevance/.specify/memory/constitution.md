<!-- Sync Impact Report: Version 1.0.1, added traceability requirements and refined principles -->
# Prior Authorization Evidence Assistant Constitution

## Core Principles

### HUMAN-IN-THE-LOOP ONLY
The system must never approve, deny, or make a final clinical or coverage determination. Every agent that touches medical necessity must output a `human_review_required` flag and may only label evidence as present/absent/unclear or ambiguous — never "approved" or "denied". Any code path that could be interpreted as an automated decision must be rejected at review time.

### GROUNDED, CITED OUTPUTS ONLY
No agent may generate a clinical or policy claim without a traceable citation to a source document, chunk ID, and confidence score. If retrieval confidence falls below a defined threshold, the system must return "Insufficient Evidence" rather than fabricate an answer. Unsupported answers are treated as a critical defect.

### FULL AUDITABILITY
Every agent invocation must be logged with: agent name, input hash, model + version, prompt version, retrieved source IDs, confidence score, output, and timestamp. Logs are immutable/append‑only and must be queryable by case_id for the Auditor and QA/Test Engineer personas.

### TEST-DRIVEN REQUIREMENTS
Every functional requirement in spec.md must be traceable to at least one automated test. Adversarial cases (no evidence found, contradictory evidence, low‑confidence retrieval, incomplete case) are first‑class test scenarios, not edge cases added later.

### NO REAL PHI IN DEVELOPMENT
All development, testing, and CI environments use synthetic member/provider/clinical data only. Any ingestion pathway must support a "synthetic mode" flag, and real PHI ingestion is out of scope for this build.

### SECURITY BY DEFAULT
Role‑based access control aligned to the seven personas (Intake Associate, Nurse Reviewer, Medical Director, Provider Relations, Operations Manager, Auditor, QA/Test Engineer). Encryption in transit (TLS 1.2+) and at rest (AES‑256) for all documents, embeddings, and case metadata. Secrets must never be hard‑coded; use a secrets manager abstraction from day one.
<!-- Example: Text I/O ensures debuggability; Structured logging required; Or: MAJOR.MINOR.BUILD format; Or: Start simple, YAGNI principles -->

## Additional Constraints
<!-- Example: Additional Constraints, Security Requirements, Performance Standards, etc. -->

TODO: Define additional security, compliance, and performance constraints.
<!-- Example: Technology stack requirements, compliance standards, deployment policies, etc. -->

## Development Workflow
<!-- Example: Development Workflow, Review Process, Quality Gates, etc. -->

TODO: Outline code review process, testing gates, and deployment approvals.
<!-- Example: Code review requirements, testing gates, deployment approval process, etc. -->

## Governance
<!-- Example: Constitution supersedes all other practices; Amendments require documentation, approval, migration plan -->

Amendments require explicit justification recorded in the constitution's changelog; they cannot be silently overridden by a later plan or task.
<!-- Example: All PRs/reviews must verify compliance; Complexity must be justified; Use [GUIDANCE_FILE] for runtime development guidance -->

**Version**: 1.0.0 | **Ratified**: TODO(RATIFICATION_DATE) | **Last Amended**: 2026-07-06
<!-- Example: Version: 2.1.1 | Ratified: 2025-06-13 | Last Amended: 2025-07-16 -->
