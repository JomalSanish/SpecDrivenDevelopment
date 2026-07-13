"""
pa-evidence-assistant backend
FastAPI application entry point — Phase 6.

Phase 6 additions:
  - SLA escalation background task (T031) via asyncio lifespan
  - Operations Dashboard routes: /api/v1/ops/* (T032a)
  - Audit trail routes: /api/v1/audit/* (T032b)
  - Readiness probe: /health/readiness (T029 WorkflowAgent)
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api import admin_routes, audit_routes, intake_routes, ops_routes, review_routes, document_routes

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Application lifespan — starts SLA background task (T031)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start background services on startup; cancel cleanly on shutdown."""
    from src.services.sla_service import run_sla_check_loop

    logger.info("Starting SLA check background task…")
    sla_task = asyncio.create_task(run_sla_check_loop())

    try:
        yield
    finally:
        logger.info("Shutting down SLA check background task…")
        sla_task.cancel()
        try:
            await sla_task
        except asyncio.CancelledError:
            pass


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="PA Evidence Assistant API",
    description=(
        "Elevance Prior Authorization Evidence Assistant — "
        "payer-side PA processing with fully local RAG. "
        "Phase 6: AuditLog, SLA escalation, Operations Dashboard."
    ),
    version="0.3.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Phase 2 routers
app.include_router(intake_routes.router)
app.include_router(review_routes.router)
app.include_router(ops_routes.router)
app.include_router(audit_routes.router)
app.include_router(admin_routes.router)
app.include_router(document_routes.router, prefix="/api/v1")


# ---------------------------------------------------------------------------
# Health endpoints
# ---------------------------------------------------------------------------

@app.get("/health", tags=["Health"])
async def health_check() -> dict:
    """Liveness probe — fast, no DB call."""
    return {"status": "ok", "service": "pa-evidence-assistant", "version": "0.3.0"}


@app.get("/health/readiness", tags=["Health"])
async def readiness_check() -> dict:
    """
    Deployment readiness probe (T029 — WorkflowAgent).

    Probes: Ollama LLM, TEI Embedding, Qdrant, MinIO.
    All must be reachable for the full pipeline to operate.
    Constitution §II: all probe targets are local endpoints only.
    """
    from src.agents.workflow_agent import WorkflowAgent

    agent = WorkflowAgent()
    report = await agent.check_readiness()
    return report.as_dict()

