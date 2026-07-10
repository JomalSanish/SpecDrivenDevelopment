# PA Evidence Assistant — Backend

## Phase 1 Setup

### Prerequisites
- Python 3.11+
- Docker & Docker Compose (for infrastructure services)

### Local Dev Setup

```bash
# 1. Copy secrets template
cp .env.local.example .env.local
# (Edit .env.local if you need non-default values)

# 2. Start all local infrastructure
cd ..
docker-compose up -d

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Run database migrations
alembic upgrade head

# 5. Start the API server
uvicorn src.main:app --reload
```

### Running Tests

```bash
pytest tests/
```

### Validating Phase 1

```bash
# From repo root — verifies secrets, Qdrant, TEI, and Ollama
python scripts/validate_phase1.py
```

### Project Structure

```
backend/
├── src/
│   ├── main.py              # FastAPI app entry point
│   ├── core/
│   │   ├── config.py        # pydantic-settings
│   │   └── secrets.py       # Secrets-manager abstraction (Vault / Env)
│   ├── models/
│   │   └── core.py          # SQLAlchemy base + shared types
│   ├── api/                 # Route handlers (Phase 2+)
│   ├── agents/              # Agent implementations (Phase 2+)
│   └── services/            # Service layer (Phase 2+)
├── alembic/                 # Database migrations
├── tests/
│   └── unit/
│       └── test_secrets.py  # Phase 1 secrets unit tests
├── alembic.ini
├── pytest.ini
└── requirements.txt
```
