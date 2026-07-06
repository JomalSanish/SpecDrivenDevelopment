# Quickstart Validation Guide: Prior Authorization Evidence Assistant

This guide describes how to validate the end-to-end multi-agent architecture locally using Docker Compose and synthetic data.

## Prerequisites
- Docker and Docker Compose installed.
- Python 3.12+ (for local CLI tooling).
- Node.js 20+ (for local frontend dev, optional if using Docker).
- Anthropic API Key (Claude).

## 1. Setup & Initialization

1. Clone the repository and navigate to the root directory.
2. Create a local environment file:
   ```bash
   cp .env.example .env
   # Edit .env to add your ANTHROPIC_API_KEY
   # Ensure SYNTHETIC_DATA_ONLY=true is set
   ```
3. Boot the infrastructure (Postgres/pgvector, Redis for Celery) and the agent services:
   ```bash
   docker-compose up -d
   ```
4. Seed the vector database with synthetic medical policy documents:
   ```bash
   python scripts/seed_kb.py --policies synthetic_policies/
   ```

## 2. Validation Scenarios

### Scenario A: Intake Completeness Check (Missing Documents)
**Goal**: Verify the Intake Agent catches missing clinical notes.

1. **Submit an incomplete case**:
   ```bash
   curl -X POST http://localhost:8000/cases -H "Content-Type: application/json" -d '{
     "member_id": "SYN-12345",
     "provider_id": "PRV-999",
     "request_type": "imaging",
     "cpt_hcpcs_codes": ["70551"],
     "icd_10_codes": ["G43.909"]
   }'
   ```
2. **Check completeness**:
   ```bash
   curl -X GET http://localhost:8000/cases/<case_id>/completeness
   ```
   **Expected Outcome**: Returns `{"is_complete": false, "missing_fields": ["clinical_notes"]}` and status is `Intake Review`.

### Scenario B: Full Pipeline Execution (Happy Path)
**Goal**: Verify all 5 agents execute sequentially, retrieve evidence, flag for human review, and route to Nurse queue.

1. **Upload synthetic clinical notes to a complete case**:
   ```bash
   curl -X POST http://localhost:8000/cases/<case_id>/documents -F "file=@synthetic_data/mri_brain_notes.pdf"
   ```
2. **Wait for async pipeline completion** (poll routing endpoint):
   ```bash
   curl -X GET http://localhost:8000/cases/<case_id>/routing
   ```
   **Expected Outcome**: Returns `{"queue": "Nurse Review", "confidence": 0.95}`.
3. **Verify Gap Analysis (No approvals!)**:
   ```bash
   curl -X GET http://localhost:8000/cases/<case_id>/gap-analysis
   ```
   **Expected Outcome**: Checklist shows matched criteria.

### Scenario C: UI Dashboard Review
**Goal**: Verify the React frontend displays the correct queue for the Nurse persona.

1. Open `http://localhost:3000` in a browser.
2. Select "Login as Nurse Reviewer" (mocked auth).
3. **Expected Outcome**: The case from Scenario B appears in the queue. Clicking it opens the Case Detail View showing the Evidence Table and highlighted citations in the Document Viewer.

### Scenario D: Audit Trail Verification
**Goal**: Ensure compliance by checking the immutable agent logs.

1. **Query the Audit API**:
   ```bash
   curl -X GET http://localhost:8000/cases/<case_id>/audit
   ```
2. **Expected Outcome**: A JSON array containing entries for all 5 agents (Intake, RAG, Reasoning, Summary, Workflow) with timestamps, prompt hashes, and model versions.
