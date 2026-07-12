"""
pa-evidence-assistant backend
FastAPI application entry point.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api import admin_routes, intake_routes, review_routes

app = FastAPI(
    title="PA Evidence Assistant API",
    description="Elevance Prior Authorization Evidence Assistant — payer-side PA processing with fully local RAG.",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Phase 2 routers
app.include_router(admin_routes.router)
app.include_router(intake_routes.router)

# Phase 5 routers
app.include_router(review_routes.router)


@app.get("/health", tags=["Health"])
async def health_check() -> dict:
    """Liveness probe."""
    return {"status": "ok", "service": "pa-evidence-assistant"}
