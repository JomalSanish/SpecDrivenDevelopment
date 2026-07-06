from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from shared.db import get_db, Base, engine
from services.orchestration_api.routers import cases, completeness

from sqlalchemy import text

# In a real app we'd run alembic, but for dev scaffold we can just create tables
with engine.connect() as conn:
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    conn.commit()
    
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Prior Authorization Evidence Assistant API",
    version="1.0.0",
    description="API Gateway orchestrating the 5-agent pipeline for PA cases."
)

app.include_router(cases.router, prefix="/cases", tags=["cases"])
app.include_router(completeness.router, prefix="/cases", tags=["completeness"])

@app.get("/health")
def health_check():
    return {"status": "ok"}
