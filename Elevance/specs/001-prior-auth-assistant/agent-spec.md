# Agent Specification: Prior Authorization Evidence Assistant

The system comprises 5 specialized orchestration agents, each deployed as an independent FastAPI microservice.

## 1. Intake & Classification Agent
- **Purpose**: Classify incoming cases and determine initial completeness before any clinical reasoning begins.
- **Responsibilities**:
  - Extract request type (e.g., advanced imaging, DME).
  - Verify presence of required fields (e.g., provider clinical notes).
  - Flag potential duplicate cases.
- **Inputs**: Case metadata (ICD-10, CPT), attached document list.
- **Outputs**: `status` ("Intake Review" if incomplete, or "Ready for Evidence Review"), `missing_fields` array.
- **Knowledge Sources**: Hardcoded intake rules per request type.
- **Explicit Constraints**: Operates solely on document metadata, not clinical text.
- **Trigger**: New case created or new document uploaded via API Gateway.
- **Hand-off**: If complete, triggers the Evidence Retrieval RAG Agent via async queue message.

## 2. Evidence Retrieval RAG Agent
- **Purpose**: Retrieve the most relevant clinical text chunks and policy rules matching the case context.
- **Responsibilities**:
  - Vectorize query components (diagnoses + procedures).
  - Query `pgvector` for matching chunks in PolicyDocuments and Case Documents.
  - Return citations and initial retrieval confidence scores.
- **Inputs**: Case ID, extracted metadata, user query.
- **Outputs**: `EvidenceItem` array with `matched_text`, `source`, `confidence`, and `citation_ref`.
- **Knowledge Sources**: `PolicyDocument` index, `Document` index.
- **Explicit Constraints**: Must return "Insufficient Evidence" if max similarity score is below threshold; NO hallucinated facts.
- **Trigger**: Called by the Pipeline Orchestrator once case is "Ready for Evidence Review".
- **Hand-off**: Passes `EvidenceItem` array to the Policy Reasoning & Gap Agent.

## 3. Policy Reasoning & Gap Agent
- **Purpose**: Map retrieved evidence to specific medical policy criteria to identify clinical gaps.
- **Responsibilities**:
  - Compare `EvidenceItem` arrays against `PolicyDocument` criteria list.
  - Produce a checklist evaluating if each criterion is `present`, `absent`, or `unclear`.
  - Detect contradictory evidence (e.g., "History of PT" vs "No prior therapy").
- **Inputs**: `EvidenceItem` array, Policy Criteria checklist.
- **Outputs**: `GapChecklistItem` array, `conflict_detected` boolean.
- **Knowledge Sources**: Anthropic Claude API (via provider-agnostic interface).
- **Explicit Constraints**: **CRITICAL:** MUST NEVER APPROVE/DENY.
- **Trigger**: Invoked upon successful completion of the Evidence Retrieval Agent.
- **Hand-off**: Passes checklist payload to Reviewer Summary & Communication Agent.

## 4. Reviewer Summary & Communication Agent
- **Purpose**: Generate human-readable artifacts from the structured gap checklist.
- **Responsibilities**:
  - Draft a concise case summary for the Nurse or Medical Director.
  - Draft a provider-facing missing-document request using neutral, non-punitive tone.
  - Generate escalation notes if contradictions were found.
- **Inputs**: `GapChecklistItem` array, `conflict_detected` flag.
- **Outputs**: `CaseSummary` object (containing `summary_text` and `evidence_refs`), `provider_draft` string, `escalation_note` string.
- **Knowledge Sources**: Anthropic Claude API (summarization prompts).
- **Explicit Constraints**: Provider draft must neutrally state *what* is missing, not *why* the case is bad.
- **Trigger**: Invoked after Policy Reasoning is complete.
- **Hand-off**: Stores drafts in DB and triggers Workflow, Audit & Deployment Readiness Agent.

## 5. Workflow, Audit & Deployment Readiness Agent
- **Purpose**: Finalize the pipeline execution, assign the case to a queue, and guarantee audit compliance.
- **Responsibilities**:
  - Determine queue routing (Intake, Nurse, MD Review) based on output from previous agents.
  - Compute a final `routing_confidence_score`.
  - Finalize all `AuditLogEntry` records (hashing inputs/outputs to ensure immutability).
- **Inputs**: Outputs from all previous agents, conflict flags, confidence scores.
- **Outputs**: `RoutingDecision` entity.
- **Knowledge Sources**: Routing rule engine.
- **Explicit Constraints**: Cases with `conflict_detected` MUST route to Medical Director Review. Every case MUST route to a human queue (Nurse Review or Medical Director Review); no code path may bypass human review.
- **Trigger**: Final step in the async pipeline.
- **Hand-off**: Updates `Case.status` and `RoutingDecision` in Postgres; completes the pipeline execution for the Reviewer Dashboard to poll.
