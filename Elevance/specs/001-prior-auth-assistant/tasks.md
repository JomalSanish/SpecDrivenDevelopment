# Implementation Tasks: Prior Authorization Evidence Assistant

**Feature**: Prior Authorization Evidence Assistant
**Plan**: `plan.md`
**Spec**: `spec.md`

## Phase 1: Foundation (Scaffold, DB, Orchestration)
Goal: Establish the repo, Postgres+pgvector, data models, and the core orchestration API.

- [x] T001 Initialize backend FastAPI repository scaffold in `backend/pyproject.toml`
- [x] T002 [P] Initialize React+TS frontend repository scaffold in `frontend/package.json`
- [x] T003 Set up Postgres 16 with pgvector and Docker Compose in `docker-compose.yml`
- [x] T004 [P] Create SQLAlchemy Base and database connection utility in `backend/shared/db.py`
- [x] T004a [FR-017] Implement Postgres table partitioning and retention policies for audit logs
- [x] T005 Define `Case` and `RoutingDecision` entities matching data-model.md in `backend/shared/models/case.py`
- [x] T006 Define `Document` and `PolicyDocument` entities in `backend/shared/models/document.py`
- [x] T007 [P] Define `EvidenceItem`, `GapChecklistItem`, and `AuditLogEntry` entities in `backend/shared/models/evidence.py`
- [x] T008 Generate initial Alembic migrations for all models in `backend/alembic/versions/`
- [x] T009 Scaffold the Case Orchestration API Gateway service in `backend/services/orchestration-api/main.py`
- [x] T010 Implement `/cases` POST endpoint to create a case in `backend/services/orchestration-api/routers/cases.py`

## Phase 2: Intake & Classification Agent [US1]
Goal: Automate completeness checks and missing-document detection at case creation.

- [x] T011 [US1] Scaffold Intake & Classification Agent FastAPI service in `backend/services/agent-intake/main.py`
- [x] T012 [P] [US1] Implement mocked OCR parsing interface in `backend/services/agent-intake/ocr_mock.py`
- [x] T012a [FR-002] Implement duplicate case detection logic in `backend/services/agent-intake/classifier.py`
- [x] T013 [US1] Implement classification logic to determine request type and completeness in `backend/services/agent-intake/classifier.py`
- [x] T014 [US1] Implement `/cases/{case_id}/completeness` endpoint returning missing fields in `backend/services/orchestration-api/routers/completeness.py`
- [x] T015 [US1] Create integration test for missing document detection in `backend/tests/integration/test_intake_completeness.py`

## Phase 3: Document Ingestion & Evidence Retrieval RAG Agent [US2]
Goal: Map policy to case evidence without making a decision.

- [x] T016 [US2] Scaffold Evidence Retrieval RAG Agent FastAPI service in `backend/services/agent-rag/main.py`
- [x] T017 [P] [US2] Implement chunking strategy for clinical notes and policy docs in `backend/services/agent-rag/chunking.py`
- [x] T018 [US2] Implement embedding generation and pgvector insertion in `backend/services/agent-rag/embeddings.py`
- [x] T019 [US2] Implement Hybrid Search (RRF semantic + keyword) in `backend/services/agent-rag/search.py`
- [x] T020 [P] [US2] Implement citation formatter (returning source name and page/section) in `backend/services/agent-rag/citation.py`
- [x] T021 [US2] Implement `/cases/{case_id}/evidence` endpoint in `backend/services/orchestration-api/routers/evidence.py`

## Phase 4: Policy Reasoning & Gap Agent [US2] [US3] [US4]
Goal: Evaluate evidence against policy criteria (present/absent/unclear) and flag ambiguities.

- [x] T022 [US2] Scaffold Policy Reasoning Agent FastAPI service in `backend/services/agent-reasoning/main.py`
- [x] T023 [US2] Implement provider-agnostic LLM interface for Anthropic Claude in `backend/shared/llm_client.py`
- [x] T024 [P] [US2] Implement checklist comparison logic generating `GapChecklistItem` in `backend/services/agent-reasoning/gap_analyzer.py`
- [x] T025 [US4] Implement contradictory evidence detection logic (sets `conflict_detected=true`) in `backend/services/agent-reasoning/conflict_detector.py`
- [x] T026 [US2] Implement `/cases/{case_id}/gap-analysis` endpoint returning the gap checklist in `backend/services/orchestration-api/routers/gap.py`
- [x] T027 [US2] Write explicit test ensuring agent NEVER emits approve/deny fields in `backend/tests/unit/test_reasoning_no_approval.py`

## Phase 5: Reviewer Summary & Communication Agent [US2]
Goal: Draft natural language summaries and missing document requests.

- [ ] T028 [US2] Scaffold Reviewer Summary Agent FastAPI service in `backend/services/agent-summary/main.py`
- [ ] T029 [P] [US2] Implement case summary generation prompt and logic in `backend/services/agent-summary/generators/summary.py`
- [ ] T030 [P] [US2] Implement neutral-tone missing document request draft generator in `backend/services/agent-summary/generators/drafts.py`
- [ ] T031 [P] [US4] Implement escalation note generator for conflict scenarios in `backend/services/agent-summary/generators/escalation.py`
- [ ] T032 [US2] Implement `/cases/{case_id}/summary` endpoint in `backend/services/orchestration-api/routers/summary.py`

## Phase 6: Workflow, Audit & Deployment Readiness Agent [US5] [US6]
Goal: Route cases based on confidence scores and enforce immutable audit trails.

- [ ] T033 [US5] Scaffold Workflow & Audit Agent FastAPI service in `backend/services/agent-workflow/main.py`
- [ ] T034 [US5] Implement routing engine logic based on confidence and conflict flags in `backend/services/agent-workflow/router.py`
- [ ] T035 [US5] Implement `/cases/{case_id}/routing` endpoint in `backend/services/orchestration-api/routers/routing.py`
- [ ] T036 [P] [US6] Implement cryptographic input/output hashing for audit entries in `backend/services/agent-workflow/audit_hasher.py`
- [ ] T037 [US6] Implement `/cases/{case_id}/audit` endpoint fetching full trail in `backend/services/orchestration-api/routers/audit.py`

## Phase 7: Reviewer Dashboard UI [US2]
Goal: Persona-based frontend interface for navigating queues and case details.

- [x] T038 [US2] Scaffold React Router with 7 persona-based views in `frontend/src/App.tsx`
- [x] T039 [P] [US2] Implement API client for Orchestration Gateway in `frontend/src/services/api.ts`
- [ ] T040 [P] [US2] Build Case Queue data table component in `frontend/src/components/QueueTable.tsx`
- [x] T041 [US2] Build Case Detail layout (Left: Summary, Center: Checklist, Right: PDF Viewer) in `frontend/src/pages/CaseDetail.tsx`
- [x] T042 [P] [US2] Build Gap Checklist Component with red/yellow/green confidence indicators in `frontend/src/components/GapChecklist.tsx`
- [ ] T043 [P] [US6] Build Audit Trail timeline drill-down modal in `frontend/src/components/AuditModal.tsx`

## Phase 8: Security & RBAC Implementation [US6]
Goal: Access control and synthetic data boundaries.

- [x] T044 [US6] Implement mock AuthProvider with the 7 static personas in `backend/shared/auth.py`
- [x] T045 [P] [US6] Add RBAC middleware to protect all orchestration API routes in `backend/services/orchestration-api/dependencies.py`
- [x] T046 [P] [US6] Add `SYNTHETIC_DATA_ONLY` enforcement toggle in config in `backend/shared/config.py`
- [ ] T046a Implement AES-256 encryption at rest for Postgres volume/DB
- [ ] T046b Implement TLS 1.2+ termination in Kubernetes ingress configuration

## Phase 9: CI/CD Pipeline
Goal: Automated tests, builds, and deployment gates.

- [x] T047 Create GitHub Actions workflow for linting (ruff, eslint) in `.github/workflows/lint.yml`
- [x] T048 [P] Create GitHub Actions workflow for tests (pytest, jest) in `.github/workflows/test.yml`
- [ ] T049 [P] Create Dockerfiles for all 5 agents and API gateway in `backend/docker/`
- [ ] T050 Create Kubernetes deployment manifests and Helm charts in `deploy/k8s/`

## Phase 10: Test Suite & Adversarial Scenarios [US3] [US4]
Goal: Verify resilience, failure modes, and safety constraints.

- [x] T051 [US3] Implement integration test: No Evidence Found (must return Insufficient Evidence) in `backend/tests/adversarial/test_no_evidence.py`
- [x] T052 [P] [US4] Implement integration test: Contradictory Evidence (must flag conflict) in `backend/tests/adversarial/test_conflict.py`
- [x] T053 [P] [US2] Implement integration test: Low Confidence Retrieval (must auto-flag for manual review) in `backend/tests/adversarial/test_low_confidence.py`
- [ ] T054 [P] [US1] Implement integration test: Incomplete Case (must stop at intake) in `backend/tests/adversarial/test_incomplete.py`
- [ ] T055 [SC-005] Implement performance and load testing suite to verify 2-minute SLA for document processing
- [ ] T056 Implement unit/integration tests for remaining un-tested functional requirements (FR-001 through FR-017)

## Dependencies
- Phase 1 must be complete before any other backend phase.
- Phase 2 (Intake) and Phase 3 (RAG) can be developed in parallel, but Phase 4 (Reasoning) requires Phase 3.
- Phase 5 (Summary) requires Phase 4.
- Phase 6 (Workflow/Audit) requires outputs from Phase 4 and 5.
- Phase 7 (UI) can proceed in parallel using mocked API responses from `contracts/openapi.yaml`.
- Phase 8 (Security), 9 (CI/CD), and 10 (Adversarial Tests) can be run concurrently with later backend phases.

## Implementation Strategy
- **MVP**: Phase 1 through 3 to prove vector retrieval and chunking accuracy against synthetic PDFs.
- **Increment 2**: Phase 4 and 5 to wire the LLM reasoning loop.
- **Increment 3**: Frontend UI, Workflow, and Security integration.
