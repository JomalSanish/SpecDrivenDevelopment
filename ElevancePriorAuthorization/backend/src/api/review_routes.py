"""
backend/src/api/review_routes.py

Nurse Review routes — Phase 5 (T022, T023, T024, T027a).

Endpoints:
  GET  /api/v1/review/cases                          T022 — list in_nurse_review cases
  GET  /api/v1/review/cases/{case_id}                T022 — case detail + completeness report
  POST /api/v1/review/cases/{case_id}/claim          T023 — atomic claim lock (409 on conflict)
  POST /api/v1/review/cases/{case_id}/decision       T024 — nurse Accept/Reject decision (403 if not claimant)
  POST /api/v1/review/cases/{case_id}/checklist/{item_id}/override  T027a — nurse checklist override

Constitution constraints:
  §I  — No automated Accept/Reject. Only a nurse can call /decision.
  §I  — Reject maps to 'returned_to_provider' — there is no terminal 'rejected' state.
  §I  — Claim uses an atomic conditional UPDATE (rows-affected==0 → 409), never read-then-write.
  §I  — /decision is rejected 403 if the requestor is not the current claimant.
  §IV — Every override writes an AuditLog row (checklist_override action_type).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.logger import AuditLogger
from src.models.case import Case, Document, ReviewStatus, AssignedQueue
from src.models.completeness import CompletenessReportItem, CompletenessStatus
from src.models.policy import Policy, PolicyRequirement

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/review", tags=["Nurse Review"])


# ---------------------------------------------------------------------------
# Pydantic schemas (review-specific — keep separate from existing schemas.py)
# ---------------------------------------------------------------------------


class CompletenessItemOut(BaseModel):
    id: uuid.UUID
    policy_requirement_id: uuid.UUID
    requirement_description: str | None = None
    status: str
    confidence_score: float
    matched_document_id: uuid.UUID | None = None
    matched_chunk_id: uuid.UUID | None = None
    reasoning_log: str | None = None
    overridden_status: str | None = None
    overridden_by_id: uuid.UUID | None = None
    overridden_at: datetime | None = None

    model_config = {"from_attributes": True}


class ReviewCaseOut(BaseModel):
    id: uuid.UUID
    member_id: str
    provider_id: str
    cpt_code: str
    icd10_code: str
    service_type: str
    requested_date: datetime
    policy_id: uuid.UUID
    policy_title: str | None = None
    review_status: str
    assigned_queue: str
    claimed_by_id: uuid.UUID | None = None
    entered_review_at: datetime | None = None
    decided_by_id: uuid.UUID | None = None
    decision_reason: str | None = None
    decision_at: datetime | None = None
    created_at: datetime
    documents: list[dict[str, Any]] = []
    completeness_report: list[CompletenessItemOut] = []

    model_config = {"from_attributes": True}


class ReviewCaseListItem(BaseModel):
    id: uuid.UUID
    member_id: str
    provider_id: str
    cpt_code: str
    icd10_code: str
    service_type: str
    requested_date: datetime
    policy_id: uuid.UUID
    policy_title: str | None = None
    review_status: str
    assigned_queue: str
    claimed_by_id: uuid.UUID | None = None
    entered_review_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ClaimResponse(BaseModel):
    status: str
    case_id: uuid.UUID
    claimed_by_id: uuid.UUID


class DecisionAction(str, Enum):
    Accept = "Accept"
    Reject = "Reject"


class DecisionRequest(BaseModel):
    """
    Nurse decision payload.

    action: "Accept" → review_status becomes "accepted"
            "Reject"  → review_status becomes "returned_to_provider"
                        (no terminal 'rejected' state — constitution §I)
    nurse_id: UUID of the nurse submitting the decision (used for lock check).
    reason_code: structured reason code (required for both Accept and Reject).
    notes: free-text notes (required for Reject, optional for Accept).
    """

    nurse_id: uuid.UUID = Field(..., description="UUID of the nurse making the decision")
    action: DecisionAction
    reason_code: str = Field(..., min_length=1, description="Structured reason code")
    notes: str | None = Field(None, description="Free-text notes (required for Reject)")


class DecisionResponse(BaseModel):
    status: str
    new_state: str


class OverrideRequest(BaseModel):
    """
    Nurse checklist override payload (CHK009).

    overridden_status: the nurse's manual assessment.
    nurse_id: UUID of the nurse performing the override (written to overridden_by_id).
    """

    overridden_status: CompletenessStatus
    nurse_id: uuid.UUID = Field(..., description="UUID of the nurse performing the override")


class OverrideResponse(BaseModel):
    status: str
    item_id: uuid.UUID
    overridden_status: str


# ---------------------------------------------------------------------------
# T022 — List cases in_nurse_review
# ---------------------------------------------------------------------------


@router.get(
    "/cases",
    response_model=list[ReviewCaseListItem],
    summary="List all cases currently in nurse review queue",
    description=(
        "Returns all cases with review_status='in_nurse_review'. "
        "Used by the Nurse Review Workspace to populate the worklist."
    ),
)
async def list_review_cases(db: AsyncSession = Depends(get_db)) -> list[ReviewCaseListItem]:
    stmt = (
        select(Case)
        .where(Case.review_status == ReviewStatus.in_nurse_review)
        .order_by(Case.entered_review_at.asc().nullslast())
    )
    result = await db.execute(stmt)
    cases = result.scalars().all()

    # Bulk-load policy titles for display
    policy_ids = {c.policy_id for c in cases}
    policy_map: dict[uuid.UUID, str] = {}
    if policy_ids:
        pol_stmt = select(Policy).where(Policy.id.in_(policy_ids))
        pol_result = await db.execute(pol_stmt)
        for pol in pol_result.scalars().all():
            policy_map[pol.id] = pol.title

    return [
        ReviewCaseListItem(
            id=c.id,
            member_id=c.member_id,
            provider_id=c.provider_id,
            cpt_code=c.cpt_code,
            icd10_code=c.icd10_code,
            service_type=c.service_type,
            requested_date=c.requested_date,
            policy_id=c.policy_id,
            policy_title=policy_map.get(c.policy_id),
            review_status=c.review_status.value,
            assigned_queue=c.assigned_queue.value,
            claimed_by_id=c.claimed_by_id,
            entered_review_at=c.entered_review_at,
            created_at=c.created_at,
        )
        for c in cases
    ]


# ---------------------------------------------------------------------------
# T022 — Case detail with completeness report
# ---------------------------------------------------------------------------


@router.get(
    "/cases/{case_id}",
    response_model=ReviewCaseOut,
    summary="Fetch case details, documents, and completeness report",
    description=(
        "Returns full case data including uploaded documents and the "
        "system-generated CompletenessReport for the nurse to review."
    ),
)
async def get_review_case(
    case_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ReviewCaseOut:
    # Load case
    stmt = select(Case).where(Case.id == case_id)
    result = await db.execute(stmt)
    case = result.scalar_one_or_none()
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found.")

    # Load policy
    pol_stmt = select(Policy).where(Policy.id == case.policy_id)
    pol_result = await db.execute(pol_stmt)
    policy = pol_result.scalar_one_or_none()
    policy_title = policy.title if policy else None

    # Load documents
    doc_stmt = select(Document).where(Document.case_id == case_id)
    doc_result = await db.execute(doc_stmt)
    documents = doc_result.scalars().all()

    # Load completeness report items
    cr_stmt = select(CompletenessReportItem).where(
        CompletenessReportItem.case_id == case_id
    )
    cr_result = await db.execute(cr_stmt)
    cr_items = cr_result.scalars().all()

    # Build requirement description map
    req_ids = {item.policy_requirement_id for item in cr_items}
    req_desc_map: dict[uuid.UUID, str] = {}
    if req_ids:
        req_stmt = select(PolicyRequirement).where(PolicyRequirement.id.in_(req_ids))
        req_result = await db.execute(req_stmt)
        for req in req_result.scalars().all():
            req_desc_map[req.id] = req.description

    completeness_out = [
        CompletenessItemOut(
            id=item.id,
            policy_requirement_id=item.policy_requirement_id,
            requirement_description=req_desc_map.get(item.policy_requirement_id),
            status=item.status.value,
            confidence_score=item.confidence_score,
            matched_document_id=item.matched_document_id,
            matched_chunk_id=item.matched_chunk_id,
            reasoning_log=item.reasoning_log,
            overridden_status=item.overridden_status.value if item.overridden_status else None,
            overridden_by_id=item.overridden_by_id,
            overridden_at=item.overridden_at,
        )
        for item in cr_items
    ]

    return ReviewCaseOut(
        id=case.id,
        member_id=case.member_id,
        provider_id=case.provider_id,
        cpt_code=case.cpt_code,
        icd10_code=case.icd10_code,
        service_type=case.service_type,
        requested_date=case.requested_date,
        policy_id=case.policy_id,
        policy_title=policy_title,
        review_status=case.review_status.value,
        assigned_queue=case.assigned_queue.value,
        claimed_by_id=case.claimed_by_id,
        entered_review_at=case.entered_review_at,
        decided_by_id=case.decided_by_id,
        decision_reason=case.decision_reason,
        decision_at=case.decision_at,
        created_at=case.created_at,
        documents=[
            {
                "id": str(d.id),
                "document_type": d.document_type.value,
                "storage_path": d.storage_path,
                "uploaded_at": d.uploaded_at.isoformat(),
            }
            for d in documents
        ],
        completeness_report=completeness_out,
    )


# ---------------------------------------------------------------------------
# T023 — Atomic claim lock (no read-then-write, avoids race between nurses)
# ---------------------------------------------------------------------------


@router.post(
    "/cases/{case_id}/claim",
    response_model=ClaimResponse,
    status_code=status.HTTP_200_OK,
    summary="Atomically claim a case for nurse review",
    description=(
        "Performs an atomic conditional UPDATE: "
        "SET claimed_by_id = :nurse_id WHERE id = :case_id AND claimed_by_id IS NULL. "
        "Returns 409 Conflict if the case is already claimed by another nurse. "
        "This is a strict lock — not a read-then-write — to prevent race conditions."
    ),
)
async def claim_case(
    case_id: uuid.UUID,
    nurse_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ClaimResponse:
    # Verify case exists first
    stmt = select(Case).where(Case.id == case_id)
    result = await db.execute(stmt)
    case = result.scalar_one_or_none()
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found.")

    if case.review_status != ReviewStatus.in_nurse_review:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Case {case_id} cannot be claimed: "
                f"review_status is '{case.review_status.value}', expected 'in_nurse_review'."
            ),
        )

    # Atomic conditional UPDATE — rows-affected == 0 means already claimed
    update_stmt = (
        update(Case)
        .where(Case.id == case_id, Case.claimed_by_id.is_(None))
        .values(claimed_by_id=nurse_id)
        .execution_options(synchronize_session="fetch")
    )
    update_result = await db.execute(update_stmt)

    if update_result.rowcount == 0:
        # Either already claimed or case vanished between check and update
        # Re-fetch to provide a useful error
        stmt2 = select(Case).where(Case.id == case_id)
        res2 = await db.execute(stmt2)
        current = res2.scalar_one_or_none()
        claimant = current.claimed_by_id if current else None
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "case_already_claimed",
                "message": f"Case {case_id} is already claimed by nurse {claimant}.",
                "claimed_by_id": str(claimant) if claimant else None,
            },
        )

    # Phase 6 (T030): write AuditLog row for case_claimed
    audit = AuditLogger(db)
    await audit.log_case_claimed(case_id=case_id, nurse_id=nurse_id)

    logger.info("Case %s claimed by nurse %s", case_id, nurse_id)
    return ClaimResponse(
        status="claimed",
        case_id=case_id,
        claimed_by_id=nurse_id,
    )


# ---------------------------------------------------------------------------
# T024 — Nurse decision (Accept → accepted / Reject → returned_to_provider)
# ---------------------------------------------------------------------------


@router.post(
    "/cases/{case_id}/decision",
    response_model=DecisionResponse,
    summary="Record nurse Accept/Reject decision on a case",
    description=(
        "Records the nurse's final decision. "
        "action='Accept' → review_status='accepted'. "
        "action='Reject' → review_status='returned_to_provider' (no terminal 'rejected' state). "
        "Returns 403 Forbidden if nurse_id does not match the current claimed_by_id — "
        "only the nurse holding the lock may submit a decision."
    ),
)
async def record_decision(
    case_id: uuid.UUID,
    request: DecisionRequest,
    db: AsyncSession = Depends(get_db),
) -> DecisionResponse:
    # Load case
    stmt = select(Case).where(Case.id == case_id)
    result = await db.execute(stmt)
    case = result.scalar_one_or_none()
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found.")

    # Validate: requesting nurse must hold the claim lock (constitution §I)
    if case.claimed_by_id != request.nurse_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "not_case_claimant",
                "message": (
                    f"Nurse {request.nurse_id} does not hold the claim lock for case {case_id}. "
                    f"Current claimant: {case.claimed_by_id}."
                ),
            },
        )

    # Validate reject notes
    if request.action == DecisionAction.Reject and not request.notes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Notes are required when action is 'Reject'.",
        )

    # Map action → review_status
    # "Reject" maps to "returned_to_provider" — no terminal 'rejected' state
    new_status: ReviewStatus
    if request.action == DecisionAction.Accept:
        new_status = ReviewStatus.accepted
    else:
        new_status = ReviewStatus.returned_to_provider

    # Compose decision_reason as structured JSON string (reason_code + notes)
    import json as _json
    decision_reason = _json.dumps(
        {"reason_code": request.reason_code, "notes": request.notes or ""},
        ensure_ascii=False,
    )

    # Apply update
    now = datetime.now(timezone.utc)
    upd_stmt = (
        update(Case)
        .where(Case.id == case_id)
        .values(
            review_status=new_status,
            decided_by_id=request.nurse_id,
            decision_reason=decision_reason,
            decision_at=now,
        )
        .execution_options(synchronize_session="fetch")
    )
    await db.execute(upd_stmt)

    # Phase 6 (T030): write AuditLog row for case_decision
    audit = AuditLogger(db)
    await audit.log_case_decision(
        case_id=case_id,
        nurse_id=request.nurse_id,
        action=request.action.value,
        reason_code=request.reason_code,
        notes=request.notes,
        new_status=new_status.value,
    )

    logger.info(
        "Case %s decision: action=%s new_status=%s by nurse=%s",
        case_id,
        request.action.value,
        new_status.value,
        request.nurse_id,
    )

    return DecisionResponse(status="success", new_state=new_status.value)


# ---------------------------------------------------------------------------
# T027a — Nurse checklist override (CHK009)
# ---------------------------------------------------------------------------


@router.post(
    "/cases/{case_id}/checklist/{item_id}/override",
    response_model=OverrideResponse,
    summary="Nurse manual override of a system-generated completeness checklist item",
    description=(
        "Allows a nurse to manually override the system-generated completeness status "
        "for a single checklist item. The original `status` field is NEVER mutated — "
        "only `overridden_status`, `overridden_by_id`, and `overridden_at` are set. "
        "This preserves the original agent output for audit reconstruction (CHK009). "
        "Also writes an AuditLog row with action_type='checklist_override' — "
        "this is logged locally; AuditLog model is created in Phase 6 (T028). "
        "Until Phase 6 lands, the override data is written to the completeness item only."
    ),
)
async def override_checklist_item(
    case_id: uuid.UUID,
    item_id: uuid.UUID,
    request: OverrideRequest,
    db: AsyncSession = Depends(get_db),
) -> OverrideResponse:
    # Verify case exists
    case_stmt = select(Case).where(Case.id == case_id)
    case_result = await db.execute(case_stmt)
    case = case_result.scalar_one_or_none()
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found.")

    # Load the specific completeness item, scoped to this case
    item_stmt = select(CompletenessReportItem).where(
        CompletenessReportItem.id == item_id,
        CompletenessReportItem.case_id == case_id,
    )
    item_result = await db.execute(item_stmt)
    item = item_result.scalar_one_or_none()
    if item is None:
        raise HTTPException(
            status_code=404,
            detail=f"CompletenessReportItem {item_id} not found for case {case_id}.",
        )

    # Apply override — original `status` is left untouched (CHK009)
    now = datetime.now(timezone.utc)
    upd_stmt = (
        update(CompletenessReportItem)
        .where(
            CompletenessReportItem.id == item_id,
            CompletenessReportItem.case_id == case_id,
        )
        .values(
            overridden_status=request.overridden_status,
            overridden_by_id=request.nurse_id,
            overridden_at=now,
        )
        .execution_options(synchronize_session="fetch")
    )
    await db.execute(upd_stmt)

    logger.info(
        "Checklist item %s overridden by nurse %s: new_status=%s (case=%s)",
        item_id,
        request.nurse_id,
        request.overridden_status.value,
        case_id,
    )

    # Phase 6 (T030/CHK009): write AuditLog row for checklist_override
    # Per data-model.md: details MUST include completeness_report_item_id,
    # original_status, and new_status.
    audit = AuditLogger(db)
    await audit.log_checklist_override(
        case_id=case_id,
        actor_id=str(request.nurse_id),
        completeness_report_item_id=item_id,
        original_status=item.status.value,
        new_status=request.overridden_status.value,
    )

    return OverrideResponse(
        status="success",
        item_id=item_id,
        overridden_status=request.overridden_status.value,
    )
