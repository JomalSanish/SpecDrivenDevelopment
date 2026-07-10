"""
backend/src/api/admin_routes.py

Admin routes — Policy document ingestion.

POST /api/v1/admin/policies
  Accepts a multipart-form PDF upload plus policy metadata.
  Triggers the Intake & Classification Agent to extract PolicyRequirements.
  Returns { policy_id, title, service_line_code, version, requirements }.

Contract: api.md §Admin Routes
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import PolicyIngestResponse, PolicyRequirementOut
from src.agents.intake_agent import get_intake_agent
from src.core.database import get_db
from src.models.policy import Policy, PolicyRequirement
from src.services.pdf_service import extract_text_from_pdf

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])


@router.post(
    "/policies",
    response_model=PolicyIngestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest policy document and extract requirements",
    description=(
        "Upload a PDF policy document along with metadata. "
        "The Intake & Classification Agent extracts a structured list of "
        "PolicyRequirement items using the local LLM. "
        "ALL processing is local — no external API calls (Constitution §II)."
    ),
)
async def ingest_policy(
    title: str = Form(..., description="Human-readable policy title"),
    service_line_code: str = Form(..., description="Service line code, e.g. 'MRI_LUMBAR'"),
    version: str = Form(..., description="Policy version string, e.g. '2024-Q1'"),
    sla_hours: int | None = Form(
        None, description="Optional nurse review SLA in hours (falls back to system default if unset)"
    ),
    document: UploadFile = File(..., description="Policy PDF document"),
    db: AsyncSession = Depends(get_db),
) -> PolicyIngestResponse:
    # ----------------------------------------------------------------
    # 1. Validate the upload
    # ----------------------------------------------------------------
    if document.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only PDF documents are accepted for policy ingestion.",
        )

    pdf_bytes = await document.read()
    if len(pdf_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Uploaded document is empty.",
        )

    # ----------------------------------------------------------------
    # 2. Extract text locally
    # ----------------------------------------------------------------
    policy_text = extract_text_from_pdf(pdf_bytes)
    if not policy_text.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Could not extract text from the uploaded PDF. "
                "Please ensure the document is a text-based (not scanned-image-only) PDF."
            ),
        )

    # ----------------------------------------------------------------
    # 3. Run Intake & Classification Agent (local LLM — constitution §II)
    # ----------------------------------------------------------------
    agent = get_intake_agent()
    try:
        result = await agent.extract_requirements(policy_text)
    except RuntimeError as exc:
        logger.error("Intake agent failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    # ----------------------------------------------------------------
    # 4. Persist Policy + PolicyRequirement rows
    # ----------------------------------------------------------------
    policy = Policy(
        title=title,
        service_line_code=service_line_code,
        version=version,
        sla_hours=sla_hours,
        active=True,
    )
    db.add(policy)
    await db.flush()  # get policy.id before creating requirements

    req_rows: list[PolicyRequirement] = []
    for extracted in result.requirements:
        req = PolicyRequirement(
            policy_id=policy.id,
            description=extracted.description,
            matching_criteria=extracted.matching_criteria or {},
        )
        db.add(req)
        req_rows.append(req)

    await db.flush()  # assign IDs to requirements
    await db.refresh(policy)
    for req in req_rows:
        await db.refresh(req)

    logger.info(
        "Policy ingested: id=%s title=%r requirements=%d model=%s",
        policy.id,
        title,
        len(req_rows),
        result.model_used,
    )

    # ----------------------------------------------------------------
    # 5. Return contract response
    # ----------------------------------------------------------------
    return PolicyIngestResponse(
        policy_id=policy.id,
        title=policy.title,
        service_line_code=policy.service_line_code,
        version=policy.version,
        requirements=[
            PolicyRequirementOut(
                id=r.id,
                description=r.description,
                matching_criteria=r.matching_criteria,
            )
            for r in req_rows
        ],
    )
