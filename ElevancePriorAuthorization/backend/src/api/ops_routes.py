"""
backend/src/api/ops_routes.py

Operations Dashboard routes — T032a.

Endpoints:
  GET /api/v1/ops/queues
    Queue statistics for the Operations Dashboard:
      - unassigned: in_nurse_review AND claimed_by_id IS NULL
      - claimed:    in_nurse_review AND claimed_by_id IS NOT NULL
      - escalated:  assigned_queue = escalation_manager
      - pending:    review_status = pending_verification
      - total_active: all non-terminal cases

  GET /api/v1/ops/cases?member_id=...&cpt_code=...
    Search/filter cases by member_id and/or cpt_code (optional, combinable).
    Returns lightweight list items for the dashboard table view.

Contract: api.md §Operations & Audit Routes
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.models.case import Case, ReviewStatus, AssignedQueue

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ops", tags=["Operations"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class QueueStats(BaseModel):
    unassigned: int
    claimed: int
    escalated: int
    pending_verification: int
    total_active: int


class OpsCaseItem(BaseModel):
    id: uuid.UUID
    member_id: str
    provider_id: str
    cpt_code: str
    icd10_code: str
    service_type: str
    requested_date: datetime
    review_status: str
    assigned_queue: str
    claimed_by_id: Optional[uuid.UUID] = None
    entered_review_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# T032a — Queue statistics
# ---------------------------------------------------------------------------


@router.get(
    "/queues",
    response_model=QueueStats,
    summary="Queue statistics for Operations Dashboard",
    description=(
        "Returns counts: Unassigned (in nurse review, unclaimed), "
        "Claimed (in nurse review, claimed), Escalated (escalation_manager queue), "
        "Pending verification, and total active cases."
    ),
)
async def get_queue_stats(db: AsyncSession = Depends(get_db)) -> QueueStats:
    # Unassigned: in_nurse_review AND claimed_by_id IS NULL
    unassigned_q = select(func.count(Case.id)).where(
        Case.review_status == ReviewStatus.in_nurse_review,
        Case.claimed_by_id.is_(None),
    )
    unassigned = (await db.execute(unassigned_q)).scalar_one()

    # Claimed: in_nurse_review AND claimed_by_id IS NOT NULL
    claimed_q = select(func.count(Case.id)).where(
        Case.review_status == ReviewStatus.in_nurse_review,
        Case.claimed_by_id.is_not(None),
    )
    claimed = (await db.execute(claimed_q)).scalar_one()

    # Escalated: assigned_queue = escalation_manager (regardless of review_status)
    escalated_q = select(func.count(Case.id)).where(
        Case.assigned_queue == AssignedQueue.escalation_manager,
    )
    escalated = (await db.execute(escalated_q)).scalar_one()

    # Pending verification
    pending_q = select(func.count(Case.id)).where(
        Case.review_status == ReviewStatus.pending_verification,
    )
    pending = (await db.execute(pending_q)).scalar_one()

    # Total active: not accepted and not returned_to_provider
    total_q = select(func.count(Case.id)).where(
        Case.review_status.not_in([
            ReviewStatus.accepted,
            ReviewStatus.returned_to_provider,
        ])
    )
    total_active = (await db.execute(total_q)).scalar_one()

    return QueueStats(
        unassigned=unassigned,
        claimed=claimed,
        escalated=escalated,
        pending_verification=pending,
        total_active=total_active,
    )


# ---------------------------------------------------------------------------
# T032a — Case search/filter
# ---------------------------------------------------------------------------


@router.get(
    "/cases",
    response_model=list[OpsCaseItem],
    summary="Search and filter cases for Operations Dashboard",
    description=(
        "Filter cases by member_id and/or cpt_code (both optional). "
        "Returns all cases if no filters provided. "
        "Results ordered by most recently created first."
    ),
)
async def search_cases(
    member_id: Optional[str] = Query(None, description="Filter by member ID (partial match)"),
    cpt_code: Optional[str] = Query(None, description="Filter by CPT code (exact match)"),
    limit: int = Query(100, ge=1, le=500, description="Max results"),
    db: AsyncSession = Depends(get_db),
) -> list[OpsCaseItem]:
    stmt = select(Case).order_by(Case.created_at.desc()).limit(limit)

    if member_id:
        stmt = stmt.where(Case.member_id.ilike(f"%{member_id}%"))
    if cpt_code:
        stmt = stmt.where(Case.cpt_code == cpt_code)

    result = await db.execute(stmt)
    cases = result.scalars().all()

    return [
        OpsCaseItem(
            id=c.id,
            member_id=c.member_id,
            provider_id=c.provider_id,
            cpt_code=c.cpt_code,
            icd10_code=c.icd10_code,
            service_type=c.service_type,
            requested_date=c.requested_date,
            review_status=c.review_status.value,
            assigned_queue=c.assigned_queue.value,
            claimed_by_id=c.claimed_by_id,
            entered_review_at=c.entered_review_at,
            created_at=c.created_at,
        )
        for c in cases
    ]
