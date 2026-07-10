"""
pa-evidence-assistant backend
FastAPI application entry point.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="PA Evidence Assistant API",
    description="Elevance Prior Authorization Evidence Assistant — payer-side PA processing with fully local RAG.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["Health"])
async def health_check() -> dict:
    """Liveness probe."""
    return {"status": "ok", "service": "pa-evidence-assistant"}
