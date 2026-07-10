# CI/CD & Deployment Specification

## Deployment Pipeline Overview
- **Source Control**: GitHub Enterprise (or internal Git server).
- **CI System**: GitHub Actions / GitLab CI runner operating within the private network.
- **Deployment Target**: Kubernetes cluster (On-Prem/Private VPC) hosting FastAPI, React, Qdrant, MinIO, and Ollama deployments.

## Automated Security & Compliance Gates
- **Public API Network Blocking**: The CI environment and Production Kubernetes pods MUST be configured with egress rules that block outbound traffic to known public LLM API endpoints (e.g., `api.openai.com`, `api.anthropic.com`).
- **Static Code Analysis (AST Check)**: The CI pipeline MUST include a custom static analysis step (e.g., Semgrep rule or AST parser) that fails the build if any HTTP request library (like `requests`, `httpx`, `aiohttp`) attempts to call a public LLM/embedding API endpoint.
- **Secrets Scanning**: Automated scanning (e.g., TruffleHog) runs on every commit to ensure no connection strings or credentials have been leaked.

## Infrastructure as Code (IaC)
- All services (Qdrant, MinIO, PostgreSQL, vLLM) are deployed using declarative IaC (Terraform or Helm Charts).
- Database migrations are executed automatically via Alembic during the deployment phase, halting deployment if a migration fails.

## Zero Downtime Deployments
- Frontend and Backend applications are deployed using rolling updates.
- Infrastructure updates (Qdrant, LLM models) are blue/green deployed to ensure the RAG pipeline is never offline for in-flight cases.
