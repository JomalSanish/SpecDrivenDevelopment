# Implementation Plan: Prior Authorization Evidence Assistant

**Branch**: `001-prior-auth-assistant` | **Date**: 2026-07-06 | **Spec**: [spec.md](file:///C:/Users/jomal/Files/Projects/SpecDrivenDevelopment/Elevance/specs/001-prior-auth-assistant/spec.md)

**Input**: Feature specification from `/specs/001-prior-auth-assistant/spec.md`

## Summary

The Prior Authorization Evidence Assistant is a RAG-and-multi-agent system that helps healthcare payer operations staff prepare and triage prior authorization cases without making automated clinical decisions. It ingests PA cases, extracts relevant documentation, maps evidence to medical policy, surfaces missing information, and routes cases.

## Technical Context

**Language/Version**: Python 3.12, TypeScript 5+

**Primary Dependencies**: 
- Backend: FastAPI
- Frontend: React
- Orchestration: Docker, Celery (or async task runner)

**Storage**: Postgres 16 with `pgvector`

**Testing**: Pytest (Backend), Jest/React Testing Library (Frontend)

**Target Platform**: Kubernetes-ready, containerized services

**Project Type**: Microservices architecture + Frontend SPA

**External Interfaces**: 
- Mock OCR interface must strictly return the `OcrExtractionResult` JSON contract defined in `data-model.md`.

**Performance Goals**: Support fast ingestion and UI rendering; Celery handles long-running retrieval/RAG async workloads.

**Constraints**: Synthetic data only for dev/test; strict RBAC; complete auditability per case.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **HUMAN-IN-THE-LOOP ONLY**: No agent determines approval/denial. All systems explicitly support a human decision-maker.
- **GROUNDED, CITED OUTPUTS ONLY**: The RAG pipeline requires citation output and flags insufficient evidence.
- **FULL AUDITABILITY**: Postgres and the Audit API provide full agent traceability.
- **TEST-DRIVEN REQUIREMENTS**: CI/CD pipeline enforces testing (unit, integration, adversarial).
- **NO REAL PHI IN DEVELOPMENT**: Dev/test environments mandate synthetic data mode.
- **SECURITY BY DEFAULT**: Role-Based Access Control and data encryption designed in from day one.

## Project Structure

### Documentation (this feature)

```text
specs/001-prior-auth-assistant/
├── spec.md                   # Core Requirements
├── plan.md                   # This file
├── data-model.md             # Entities and schema mapping
├── contracts/openapi.yaml    # Internal API contracts
├── agent-spec.md             # Multi-agent architecture definitions
├── rag-pipeline.md           # Retrieval-Augmented Generation design
├── ui-spec.md                # Reviewer dashboard design
├── security-compliance.md    # RBAC, audit, and encryption rules
├── cicd-deployment.md        # Deployment and testing pipeline
├── research.md               # Areas needing tech spikes
└── quickstart.md             # Validation and execution guide
```

### Source Code (repository root)

```text
backend/
├── services/
│   ├── orchestration-api/      # API Gateway & Case State orchestrator
│   ├── agent-intake/           # Intake & Classification Agent
│   ├── agent-rag/              # Evidence Retrieval Agent
│   ├── agent-reasoning/        # Policy Reasoning & Gap Agent
│   ├── agent-summary/          # Reviewer Summary & Communication Agent
│   └── agent-workflow/         # Workflow, Audit & Deployment Agent
└── shared/                     # Shared models, db access, and utils

frontend/
├── src/
│   ├── components/             # UI Components (Tables, Evidence Panels)
│   ├── pages/                  # Persona-based Queue Views & Case Details
│   └── services/               # API clients
└── tests/
```

**Structure Decision**: Microservices pattern mapped 1-to-1 with agent boundaries. Shared components encapsulate data access, while each agent exposes a FastAPI-driven REST interface or consumes Celery tasks.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| 6 Backend Services | Multi-agent separation of concerns | Monolith lacks independent prompt/model versioning per agent constraint. |
