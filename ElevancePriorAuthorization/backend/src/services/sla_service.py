"""
backend/src/services/sla_service.py

SLA Escalation Service — T031.

Runs as a periodic background task (APScheduler / asyncio loop).
Scans cases that are `in_nurse_review` and computes whether their SLA has
been breached by comparing Case.entered_review_at against Policy.sla_hours
(or a global default of 48 h when Policy.sla_hours is NULL).

On breach:
  - Sets Case.assigned_queue  → AssignedQueue.escalation_manager
  - Clears Case.claimed_by_id → NULL (removes from original nurse's queue)
  - Writes an AuditLog row    → action_type = 'sla_escalation'

Constitution §I: SLA escalation ONLY re-routes the case to a different queue.
It does NOT make a clinical Accept/Reject decision (no automated denial).

data-model.md: entered_review_at is the SLA anchor — NOT claimed_by_id.
An unclaimed case can still breach SLA and escalate.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logger import log_audit_event
from src.models.audit import AuditActionType
from src.models.case import Case, AssignedQueue, ReviewStatus
from src.models.policy import Policy

logger = logging.getLogger(__name__)

# Global SLA fallback when Policy.sla_hours is NULL
SLA_DEFAULT_HOURS: int = 48

# How often the background checker polls (seconds)
SLA_CHECK_INTERVAL_SECONDS: int = 300  # every 5 minutes


# ---------------------------------------------------------------------------
# Core escalation logic
# ---------------------------------------------------------------------------


async def escalate_sla_breached_cases(session: AsyncSession) -> list[uuid.UUID]:
    """
    Identify and escalate all in-review cases whose SLA has been breached.

    Returns list of case UUIDs that were escalated in this pass.

    Steps:
      1. Load all cases with review_status=in_nurse_review.
      2. For each, load the associated Policy to get sla_hours.
      3. Compute hours since entered_review_at.
      4. If hours > effective_sla_hours:
           a. UPDATE cases SET assigned_queue='escalation_manager',
                              claimed_by_id=NULL
           b. Write AuditLog row.

    NOTE: This runs in a single transaction per call so partial failures
    roll back cleanly.  For very large queues a cursor-based approach
    is preferred — this implementation is sufficient for payer-scale volumes.
    """
    escalated: list[uuid.UUID] = []
    now = datetime.now(timezone.utc)

    # Load all in-nurse-review cases that still have an entered_review_at
    stmt = select(Case).where(
        Case.review_status == ReviewStatus.in_nurse_review,
        Case.entered_review_at.is_not(None),
        Case.assigned_queue != AssignedQueue.escalation_manager,
    )
    result = await session.execute(stmt)
    cases = result.scalars().all()

    for case in cases:
        # Load policy for sla_hours
        pol_stmt = select(Policy).where(Policy.id == case.policy_id)
        pol_result = await session.execute(pol_stmt)
        policy = pol_result.scalar_one_or_none()

        effective_sla = (
            policy.sla_hours if (policy and policy.sla_hours) else SLA_DEFAULT_HOURS
        )

        # entered_review_at must be timezone-aware for comparison
        entered_at = case.entered_review_at
        if entered_at.tzinfo is None:
            entered_at = entered_at.replace(tzinfo=timezone.utc)

        hours_elapsed = (now - entered_at).total_seconds() / 3600.0

        if hours_elapsed <= effective_sla:
            continue  # Not breached — skip

        previous_queue = case.assigned_queue.value

        # Atomic update: set escalation_manager, clear claimed_by_id
        upd_stmt = (
            update(Case)
            .where(Case.id == case.id)
            .values(
                assigned_queue=AssignedQueue.escalation_manager,
                claimed_by_id=None,
            )
            .execution_options(synchronize_session="fetch")
        )
        await session.execute(upd_stmt)

        escalated.append(case.id)

        logger.warning(
            "SLA breach: case=%s was in review for %.1fh (SLA=%dh). "
            "Escalated to escalation_manager, claimed_by_id cleared.",
            case.id,
            hours_elapsed,
            effective_sla,
        )

        # Write audit log row (using standalone helper so it commits atomically)
        try:
            await log_audit_event(
                case_id=case.id,
                actor_id="sla_service",
                action_type=AuditActionType.sla_escalation,
                details={
                    "previous_queue": previous_queue,
                    "new_queue": AssignedQueue.escalation_manager.value,
                    "entered_review_at": entered_at.isoformat(),
                    "hours_elapsed": round(hours_elapsed, 2),
                    "sla_hours": effective_sla,
                },
            )
        except Exception:
            logger.exception(
                "Failed to write SLA escalation audit log for case=%s", case.id
            )
            # Do not re-raise — the escalation itself succeeded; audit failure
            # is non-fatal but logged for investigation.

    return escalated


# ---------------------------------------------------------------------------
# Background scheduler loop
# ---------------------------------------------------------------------------


async def run_sla_check_loop() -> None:
    """
    Infinite async loop that periodically calls escalate_sla_breached_cases.

    Intended to run as a FastAPI lifespan background task:

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            task = asyncio.create_task(run_sla_check_loop())
            yield
            task.cancel()

    The loop uses its own DB session per iteration so a single failure
    does not corrupt the next run.
    """
    from src.core.database import AsyncSessionLocal

    logger.info(
        "SLA check loop started. Interval: %ds (%.1fmin).",
        SLA_CHECK_INTERVAL_SECONDS,
        SLA_CHECK_INTERVAL_SECONDS / 60,
    )

    while True:
        await asyncio.sleep(SLA_CHECK_INTERVAL_SECONDS)
        try:
            async with AsyncSessionLocal() as session:
                escalated = await escalate_sla_breached_cases(session)
                await session.commit()
                if escalated:
                    logger.info(
                        "SLA check: escalated %d case(s): %s",
                        len(escalated),
                        [str(c) for c in escalated],
                    )
                else:
                    logger.debug("SLA check: no breaches detected.")
        except asyncio.CancelledError:
            logger.info("SLA check loop cancelled — shutting down.")
            break
        except Exception:
            logger.exception("SLA check loop encountered an error. Continuing.")
