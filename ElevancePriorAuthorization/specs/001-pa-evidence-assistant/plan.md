# Implementation Plan: pa-evidence-assistant

**Branch**: `001-pa-evidence-assistant` | **Date**: 2026-07-10 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/001-pa-evidence-assistant/spec.md`

## Summary

Build a payer-side web application (Elevance Prior Authorization Evidence Assistant) to process prior authorization requests. It leverages a fully localized, hybrid RAG pipeline (dense + BM25) to generate a completeness report against policy requirements, without ever making automated clinical decisions. A strict human-in-the-loop Nurse Review workflow ensures a human decides Accept/Reject, supported by system-generated checklists and citations.

## Technical Context

**Language/Version**: Python 3.11+ (Backend), Node.js/TypeScript (Frontend)

**Primary Dependencies**: FastAPI, React, Qdrant (self-hosted), MinIO (self-hosted object storage), vLLM/Ollama (local LLM), TEI/SentenceTransformers (local embeddings)

**Storage**: PostgreSQL (case/workflow state)

**Testing**: pytest (Backend), Jest/React Testing Library (Frontend)

**Target Platform**: Linux server (On-Prem/Private VPC)

**Project Type**: Web Service + Single Page Application

**Performance Goals**: Sub-second hybrid retrieval latency; <5s completeness report generation per case document set

**Constraints**: ZERO public API calls for RAG/inference; strictly on-prem/VPC deployed; Strict human-in-the-loop constraints

**Scale/Scope**: Payer-scale prior auth ingestion; isolated vector collections per case

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [x] **Human-in-the-loop**: No automated approve/deny/accept/reject outcomes. Uses explicit state fields.
- [x] **Data Locality & Confidentiality**: No public/3rd-party hosted API calls for RAG/inference on case documents.
- [x] **Hybrid Retrieval**: Search paths combine dense semantic + sparse BM25 retrieval.
- [x] **Auditable Citations**: Evidence claims cite specific source documents/locations with stable UUIDs.
- [x] **Secrets Management**: Config/API keys use an abstracted secrets manager from Phase 1.
- [x] **Five-Agent Architecture**: Aligns with Intake, Retrieval, Reasoning, Reviewer Summary, Workflow.
- [x] **Spec-Driven**: Full specification set is produced before execution phase.

## Project Structure

### Documentation (this feature)

```text
specs/001-pa-evidence-assistant/
├── plan.md              # This file
├── research.md          
├── data-model.md        
├── quickstart.md        
├── contracts/           
├── agent-spec.md
├── rag-pipeline.md
├── ui-spec.md
├── security-compliance.md
├── cicd-deployment.md
└── tasks.md             
```

### Source Code (repository root)

```text
backend/
├── src/
│   ├── api/
│   ├── agents/
│   ├── models/
│   ├── services/
│   └── core/ (secrets, config)
└── tests/

frontend/
├── src/
│   ├── components/
│   ├── pages/ (Nurse Review, Operations)
│   └── services/
└── tests/

infrastructure/
├── qdrant/
├── minio/
└── llm_serving/ (vLLM, TEI)
```

**Structure Decision**: Standard web application with isolated frontend/backend directories, plus an infrastructure directory to manage local services (Qdrant, MinIO, LLM serving).
