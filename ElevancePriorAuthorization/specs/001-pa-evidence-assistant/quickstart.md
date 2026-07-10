# Quickstart Validation Guide

**Prerequisites:**
- Docker & Docker Compose installed (for MinIO, Qdrant, PostgreSQL, vLLM).
- Sufficient local RAM/GPU for serving `bge-large-en-v1.5` (via TEI) and a local LLM via Ollama (llama3.1).

**1. Spin up local infrastructure**
```bash
docker-compose up -d postgres minio qdrant ollama tei
```

**2. Initialize Database and Secrets**
```bash
python scripts/init_secrets.py
alembic upgrade head
```

**3. Run Backend**
```bash
cd backend
pip install -r requirements.txt
uvicorn src.main:app --reload
```

**4. Run Frontend**
```bash
cd frontend
npm install
npm run dev
```

**5. Validation Scenario (Admin Policy Upload)**
1. Navigate to `/admin/policies`.
2. Upload a sample MRI Lumbar Spine policy PDF.
3. Verify the system extracts `PolicyRequirement` items automatically.

**6. Validation Scenario (Case Submission & Completeness)**
1. Navigate to `/intake`.
2. Submit a mock case with a dummy PDF note.
3. Wait for the `CompletenessReport` to generate.
4. Verify the case routes to the Nurse Review dashboard.
