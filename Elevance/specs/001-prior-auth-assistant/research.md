# Research Tasks: Prior Authorization Evidence Assistant

The following areas require further technical investigation before implementation begins. The results of these spikes will inform library choices and architecture refinements.

## 1. Hybrid Search Library for Postgres/pgvector
**Problem**: The RAG pipeline requires Reciprocal Rank Fusion (RRF) to combine semantic vector search (pgvector) with keyword search (Postgres Full Text Search). Implementing RRF in raw SQL can be complex and brittle.
**Research Task**: 
- Evaluate if an existing Python library (e.g., `LangChain` Postgres integration, `LlamaIndex`, or `pgvector-python` extensions) provides native, robust RRF support out-of-the-box.
- If no library is sufficient, draft the optimized raw SQL function required to merge `ts_rank` with cosine similarity scores efficiently.
**Decision Needed**: Select a specific Python library or commit to a custom SQL implementation for the Evidence Retrieval RAG Agent.

## 2. OpenAPI Tooling for FastAPI Multi-Agent Architecture
**Problem**: The system consists of 5 separate FastAPI microservices, plus an API Gateway orchestrator. We need a unified way to generate and serve the overarching OpenAPI contract (`contracts/openapi.yaml`) while keeping individual agent schemas in sync.
**Research Task**:
- Evaluate strategies for OpenAPI merging. Can we use a tool like `swagger-cli` or `redocly` to combine individual FastAPI `/openapi.json` endpoints into one central schema?
- Alternatively, investigate if a specific Python API Gateway library (e.g., `Ocelot` equivalent for Python, or just standard FastAPI router mounting) handles sub-app schema federation natively.
**Decision Needed**: Select the toolchain for maintaining and serving the consolidated API contract.

## 3. Mock OCR Interface Implementation Details
**Problem**: The Intake & Classification agent relies on a mocked OCR component to simulate extraction of clinical text from PDFs without calling a real vendor (Textract/Azure) to avoid PHI exposure and costs in dev.
**Research Task**:
- Determine the best library to simulate this. Should we just use `PyPDF2` or `pdfplumber` to pull raw text from synthetic PDF documents, wrapping it in an interface that *looks* like a vendor API?
- Define the exact JSON shape that the mocked OCR should output (e.g., bounding boxes, confidence scores) so that the downstream agents don't have to change when moving to a real vendor.
**Decision Needed**: Finalize the Python library and JSON schema for the OCR placeholder.
