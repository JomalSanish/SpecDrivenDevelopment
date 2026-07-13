"""
backend/src/api/audit_routes.py

AuditLog read-only trail endpoint — T032b.

Endpoint:
  GET /api/v1/audit/cases/{case_id}
    Returns the full, chronological AuditLog trail for a case.
    Includes timestamps, actor identities, prompts, retrieved chunk IDs,
    confidence scores, and decisions.

    Powers the Operations Dashboard audit view (User Story 4).
    Read-only — no mutations allowed on the audit trail (Constitution §IV).

Contract: api.md §Operations & Audit Routes
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.models.audit import AuditLog
from src.models.case import Case

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/audit", tags=["Audit"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class AuditLogEntry(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    actor_id: str
    action_type: str
    details: dict[str, Any]
    timestamp: datetime

    model_config = {"from_attributes": True}


class AuditTrailResponse(BaseModel):
    case_id: uuid.UUID
    total_events: int
    events: list[AuditLogEntry]


# ---------------------------------------------------------------------------
# T032b — Full read-only AuditLog trail
# ---------------------------------------------------------------------------


@router.get(
    "/cases/{case_id}",
    response_model=AuditTrailResponse,
    summary="Full read-only AuditLog trail for a case",
    description=(
        "Returns all AuditLog entries for the specified case, ordered "
        "chronologically (oldest first). "
        "Includes: LLM prompts, RAG chunk IDs, confidence scores, "
        "nurse decisions, checklist overrides, claim events, and SLA "
        "escalations. "
        "Read-only — the audit trail is immutable (Constitution §IV)."
    ),
)
async def get_audit_trail(
    case_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> AuditTrailResponse:
    # Verify case exists
    case_stmt = select(Case).where(Case.id == case_id)
    case_result = await db.execute(case_stmt)
    if case_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found.")

    # Load all audit log entries for this case, oldest first
    log_stmt = (
        select(AuditLog)
        .where(AuditLog.case_id == case_id)
        .order_by(AuditLog.timestamp.asc())
    )
    log_result = await db.execute(log_stmt)
    entries = log_result.scalars().all()

    return AuditTrailResponse(
        case_id=case_id,
        total_events=len(entries),
        events=[
            AuditLogEntry(
                id=e.id,
                case_id=e.case_id,
                actor_id=e.actor_id,
                action_type=e.action_type.value,
                details=e.details,
                timestamp=e.timestamp,
            )
            for e in entries
        ],
    )
