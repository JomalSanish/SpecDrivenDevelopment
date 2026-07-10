# Security & Compliance Specification

## Data Locality Guarantees
- **No External Egress**: The system operates exclusively within a secure on-premise or private VPC network boundary.
- **No Public APIs**: It is strictly forbidden to use OpenAI, Anthropic, Cohere, or any cloud provider's managed LLM/Embedding API for processing case documents or generating completeness reports.
- **Local Inference**: All embedding generation and LLM text generation MUST route to internally hosted endpoints (e.g., vLLM or TEI instances deployed on private infrastructure).

## PHI Handling (Dev/Test vs. Prod)
- **Production**: Real PHI is processed but isolated. Vector stores are partitioned by `case_id`.
- **Development/Test**: Real PHI NEVER appears outside of production. All testing, CI/CD, and local developer environments MUST use synthetic data only.

## Audit Logging Requirements
- Every state change in the `Case` entity MUST generate an `AuditLog` record.
- Every RAG retrieval and LLM prompt execution MUST be logged, capturing the model version, confidence scores, and retrieved chunk IDs.
- Every manual override or Accept/Reject decision by a nurse MUST be logged, recording the `actor_id`, timestamp, and any provided reasoning.

## Secrets Management
- Hardcoding credentials in code or relying on unencrypted `.env` files is prohibited.
- A centralized Secrets Manager (e.g., HashiCorp Vault) MUST be used from Phase 1 to inject connection strings for PostgreSQL, Qdrant, MinIO, and internal inference servers.
