# CI/CD and Deployment Specification: Prior Authorization Evidence Assistant

## 1. CI/CD Pipeline (GitHub Actions)

The pipeline is triggered on every Pull Request to `main` and on merges to `main`.

### Stage 1: Static Analysis
- **Linting & Formatting**: `ruff` for Python backend, `eslint` and `prettier` for React frontend.
- **Type Checking**: `mypy` for Python, `tsc` for TypeScript.
- **Security Scan**: `bandit` for Python, `npm audit` for frontend.

### Stage 2: Unit Testing
- **Backend Tests**: `pytest` covering all utility functions, Pydantic model validations, and routing logic.
- **Frontend Tests**: `jest` and React Testing Library for component rendering and state logic.

### Stage 3: Integration & Adversarial Testing
- **API Tests**: Spin up ephemeral PostgreSQL/pgvector instance; run FastAPI endpoint tests.
- **Adversarial RAG/Gap Scenarios**:
  - Feed the system explicitly contradictory synthetic evidence (must flag `conflict_detected = true`).
  - Feed the system irrelevant documents (must return `Insufficient Evidence`).
  - Attempt to inject prompts that request an "approval" decision (must fail/be rejected by guardrails).

### Stage 4: Build & Registry
- Build Docker images for the 5 agents, the API gateway, and the frontend UI.
- Push images to the container registry (e.g., GHCR, ECR) tagged with the commit SHA.

### Stage 5: Staging Deployment
- Auto-deploy the new images to the Staging Kubernetes cluster using Helm or Kustomize.
- Run smoke tests against the Staging environment.

### Stage 6: Manual Gate & Production Deploy
- Execution pauses for manual approval by a designated Tech Lead or QA Engineer.
- Upon approval, images are promoted and deployed to Production.

## 2. Deployment-Readiness Checklist
*(Aligned with the Workflow, Audit & Deployment Readiness Agent's criteria)*

- [ ] **Data Mode Confirmed**: Environment variables verified (`SYNTHETIC_DATA_ONLY=true` for non-prod).
- [ ] **Model Endpoints Configured**: LLM provider URLs and API keys correctly mounted via Secrets.
- [ ] **Vector Index Initialized**: `pgvector` extension is active and medical policy reference embeddings are pre-loaded.
- [ ] **RBAC Seeded**: The 7 default personas and test accounts exist in the auth provider.
- [ ] **Audit Trail Active**: Postgres write-only permissions verified for the `AuditLogEntry` table.
- [ ] **Adversarial Pass**: All guardrail tests (preventing automated approvals) passed in CI.
