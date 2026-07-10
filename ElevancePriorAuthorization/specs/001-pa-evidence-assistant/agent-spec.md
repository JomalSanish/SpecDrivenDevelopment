# Agent Specifications

## 1. Intake & Classification Agent
- **Inputs**: Raw unstructured PDF case documents, fax scans.
- **Outputs**: Parsed text chunks with standard metadata tags (document type, provider, date).
- **Tools**: Local OCR engine (e.g., Tesseract), local PDF parser.
- **Guardrails**: PII/PHI strict isolation (no external egress).
- **Escalation**: Flags document as unreadable if OCR fails completely.

## 2. Evidence Retrieval (RAG) Agent
- **Inputs**: `policy_requirement_checklist` items, Case Document Collection (isolated vector space).
- **Outputs**: Top-K retrieved chunks (hybrid scored).
- **Tools**: Qdrant Hybrid Search (BM25 + Dense).
- **Guardrails**: Limits search strictly to the current `case_id` scope. Treats identifier-type requirements (member ID, CPT/HCPCS, ICD-10) as requiring a sparse/BM25 hit; a dense-only match is passed downstream flagged as `keyword_miss` rather than a confirmed retrieval.
- **Escalation**: If Qdrant is unreachable, the case is held in a queued/retry state with an admin-visible alert; the agent MUST NOT fall back to any external search or embedding API.

## 3. Policy Reasoning & Gap Analysis Agent
- **Inputs**: Retrieved evidence chunks, policy requirement rule.
- **Outputs**: `CompletenessReportItem` (Present/Absent/Unclear) with reasoning and confidence score.
- **Tools**: Local LLM inference (Ollama endpoint) with few-shot reasoning prompts.
- **Guardrails**: Enforces confidence thresholds: >80% (Present), 50-80% (Unclear), <50% (Absent). For identifier-type requirements, a `keyword_miss` flag from the Retrieval Agent forces a result of Unclear regardless of dense confidence score.
- **Escalation**: Any confidence between 50-80% defaults to Unclear, forcing human review of the gap. If the local Ollama endpoint is unreachable, the case is held in a queued/retry state with an admin-visible alert rather than falling back to any external LLM API.

## 4. Reviewer Summary & Communication Agent
- **Inputs**: Nurse's Reject decision, reason code, free-text notes, original `CompletenessReport`.
- **Outputs**: Drafted provider-facing missing-document communication.
- **Tools**: Local LLM generation.
- **Guardrails**: Cannot send messages directly. Must be marked as "Draft" for Nurse/Admin approval.

## 5. Workflow/Audit & Deployment Readiness Agent
- **Inputs**: State transitions (e.g., Intake -> RAG -> Nurse Review), User actions (Claim, Accept/Reject).
- **Outputs**: Immutable `AuditLog` records.
- **Tools**: Database transaction logger.
- **Guardrails**: Rejects any state transition that attempts to bypass the Nurse Review phase (e.g., automated Accept).
