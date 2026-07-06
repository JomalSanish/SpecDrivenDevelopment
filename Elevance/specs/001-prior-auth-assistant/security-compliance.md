# Security & Compliance Specification: Prior Authorization Evidence Assistant

## 1. Role-Based Access Control (RBAC)
Access is tightly controlled via a mocked Identity Provider implementing strict RBAC for the 7 personas:
- **Intake Associate**: Read/Write access to Case Intake endpoints; no access to clinical routing APIs.
- **Nurse Reviewer**: Read access to Case, Evidence, and Gap APIs; Write access to update Checklist status.
- **Medical Director**: Same as Nurse, plus Write access to override Routing assignments.
- **Provider Relations**: Read access to Draft Summaries; no access to raw clinical notes.
- **Operations Manager**: Read access to Routing and aggregate queue metrics; no access to PII/PHI.
- **Auditor**: Read access to the Audit API; Read access to Case data for context.
- **QA/Test Engineer**: Access to synthetic test environments only.

## 2. Encryption Standards
- **In Transit**: All API communications between the frontend UI, API Gateway, and internal Agent microservices MUST use TLS 1.2 or higher. Internal service mesh encryption is required for Kubernetes deployments.
- **At Rest**: The Postgres 16 database (relational tables and `pgvector` index) MUST utilize AES-256 encryption at the volume level. Object storage for uploaded PDFs MUST also be AES-256 encrypted.

## 3. Secrets Management
- No hardcoded secrets (API keys, DB credentials) are permitted in the codebase.
- The architecture MUST abstract secrets via an interface (e.g., pulling from AWS Secrets Manager, HashiCorp Vault, or injected via Kubernetes Secrets in production; `.env` files for local Docker dev).

## 4. Synthetic Data Policy
- **Development & Testing**: The system MUST run exclusively on synthetic member, provider, and clinical data during development and CI/CD. 
- The Intake API enforces this by requiring a `synthetic_mode=true` header during non-production deployments.

## 5. Audit Log Immutability
- The `AuditLogEntry` records are write-only.
- Updates or deletes to the Audit table are strictly prohibited at the database permissions level for application roles.
- Each entry includes a cryptographic hash (`input_hash`) of the prompt and input data to detect tampering.

## 6. PHI Handling Boundary Statement
- **Scope Limit**: This project does NOT include production integration with live Electronic Medical Record (EMR) systems or real claims databases.
- Real Protected Health Information (PHI) ingestion is explicitly **OUT OF SCOPE**. Any future transition to production requires a separate HIPAA compliance audit and Business Associate Agreement (BAA) reviews for the LLM providers.
