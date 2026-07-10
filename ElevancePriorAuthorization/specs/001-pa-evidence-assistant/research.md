# Research & Decisions

Since the architecture and technical stack were explicitly provided in the requirements, no primary exploratory research was needed. The following decisions reflect the constraints provided:

## Backend Framework
**Decision**: FastAPI
**Rationale**: High performance, Python-native (essential for ML/AI agent ecosystems), and well-suited for wrapping local models (sentence-transformers, vLLM).

## Database
**Decision**: PostgreSQL
**Rationale**: Robust relational store for strict case/workflow state constraints, ensuring transactional integrity when recording human-in-the-loop decisions and SLA timers.

## RAG Infrastructure
**Decision**: Qdrant (Self-hosted) + Local BAAI/bge-large-en-v1.5 Embeddings + vLLM
**Rationale**: Adheres to strict data-locality and confidentiality rules (no external API egress). Qdrant supports native hybrid search (dense + sparse BM25) and reciprocal rank fusion, which is mandated by the feature spec.

## Secrets Management
**Decision**: HashiCorp Vault (or abstracted local KMS wrapper)
**Rationale**: Constitution principle V mandates abstracting all credentials from Day 1 to prevent any hardcoded credentials in the repository or environment variables directly.
