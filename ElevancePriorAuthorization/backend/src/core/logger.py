"""
backend/src/core/logger.py

Database transaction logger — T030.

Wraps all RAG retrievals and LLM completions with a structured audit log
write into the audit_logs table (T028 / AuditLog model).

Constitution §IV: Every RAG retrieval and LLM prompt/response MUST be
    persisted to the database so the complete audit trail is reconstructable
    independent of application logs or container stdout.

Secrets abstraction: No credentials are accessed here directly. All DB
    access flows through get_db() / AsyncSession per the existing pattern.

Usage
-----
    from src.core.logger import AuditLogger

    # In an async route or agent — pass the active session
    audit = AuditLogger(db_session)
    await audit.log_llm_completion(
        case_id=case.id,
        actor_id="reasoning_agent",
        prompt="...",
        model="phi4-mini",
        response_excerpt="...",
    )

    # Or use the convenience module-level helper that opens its own session
    from src.core.logger import log_audit_event
    await log_audit_event(
        case_id=...,
        actor_id="intake_agent",
        action_type=AuditActionType.policy_ingested,
        details={"policy_id": str(policy_id)},
    )
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.audit import AuditLog, AuditActionType

logger = logging.getLogger(__name__)


class AuditLogger:
    """
    Session-scoped audit logger.

    Accepts an active AsyncSession and appends AuditLog rows.
    The caller is responsible for committing the session (or letting the
    FastAPI get_db() dependency commit at end of request).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _write(
        self,
        case_id: uuid.UUID,
        actor_id: str,
        action_type: AuditActionType,
        details: dict[str, Any],
    ) -> AuditLog:
        """Append one AuditLog row. Caller must commit the session."""
        row = AuditLog(
            case_id=case_id,
            actor_id=actor_id,
            action_type=action_type,
            details=details,
        )
        self._session.add(row)
        # Flush so the row gets an id immediately (useful for chaining)
        await self._session.flush()
        logger.debug(
            "AuditLog written: case=%s action=%s actor=%s",
            case_id,
            action_type.value,
            actor_id,
        )
        return row

    # -----------------------------------------------------------------------
    # Convenience methods per action type
    # -----------------------------------------------------------------------

    async def log_policy_ingested(
        self,
        case_id: uuid.UUID,
        actor_id: str,
        policy_id: uuid.UUID,
        title: str,
        requirements_count: int,
    ) -> AuditLog:
        return await self._write(
            case_id=case_id,
            actor_id=actor_id,
            action_type=AuditActionType.policy_ingested,
            details={
                "policy_id": str(policy_id),
                "title": title,
                "requirements_extracted": requirements_count,
            },
        )

    async def log_case_submitted(
        self,
        case_id: uuid.UUID,
        actor_id: str,
        member_id: str,
        policy_id: uuid.UUID,
        document_count: int,
    ) -> AuditLog:
        return await self._write(
            case_id=case_id,
            actor_id=actor_id,
            action_type=AuditActionType.case_submitted,
            details={
                "member_id": member_id,
                "policy_id": str(policy_id),
                "document_count": document_count,
            },
        )

    async def log_rag_retrieval(
        self,
        case_id: uuid.UUID,
        actor_id: str,
        query: str,
        chunk_ids: list[str],
        scores: list[float],
    ) -> AuditLog:
        """Log a RAG retrieval event (dense + sparse fusion result)."""
        return await self._write(
            case_id=case_id,
            actor_id=actor_id,
            action_type=AuditActionType.rag_retrieval,
            details={
                "query": query[:500],          # cap to avoid oversized rows
                "chunk_ids": chunk_ids[:20],   # top-20 only
                "scores": [round(s, 4) for s in scores[:20]],
                "chunk_count": len(chunk_ids),
            },
        )

    async def log_llm_completion(
        self,
        case_id: uuid.UUID,
        actor_id: str,
        prompt: str,
        model: str,
        response_excerpt: str,
        extra: dict[str, Any] | None = None,
    ) -> AuditLog:
        """
        Log an LLM prompt + response.

        Constitution §IV: Full prompt and response excerpt persisted.
        The response is capped at 2 000 chars to keep row size reasonable;
        the full reasoning_log is on the CompletenessReportItem.
        """
        details: dict[str, Any] = {
            "prompt": prompt[:2000],
            "model": model,
            "response_excerpt": response_excerpt[:2000],
            "endpoint": "local_ollama",      # documents that this is local-only
        }
        if extra:
            details.update(extra)
        return await self._write(
            case_id=case_id,
            actor_id=actor_id,
            action_type=AuditActionType.llm_completion,
            details=details,
        )

    async def log_checklist_override(
        self,
        case_id: uuid.UUID,
        actor_id: str,
        completeness_report_item_id: uuid.UUID,
        original_status: str,
        new_status: str,
    ) -> AuditLog:
        """
        Log a nurse checklist override (CHK009).

        Per data-model.md: details MUST include
          completeness_report_item_id, original_status, new_status.
        """
        return await self._write(
            case_id=case_id,
            actor_id=actor_id,
            action_type=AuditActionType.checklist_override,
            details={
                "completeness_report_item_id": str(completeness_report_item_id),
                "original_status": original_status,
                "new_status": new_status,
            },
        )

    async def log_case_claimed(
        self,
        case_id: uuid.UUID,
        nurse_id: uuid.UUID,
    ) -> AuditLog:
        return await self._write(
            case_id=case_id,
            actor_id=str(nurse_id),
            action_type=AuditActionType.case_claimed,
            details={"nurse_id": str(nurse_id)},
        )

    async def log_case_decision(
        self,
        case_id: uuid.UUID,
        nurse_id: uuid.UUID,
        action: str,
        reason_code: str,
        notes: str | None,
        new_status: str,
    ) -> AuditLog:
        return await self._write(
            case_id=case_id,
            actor_id=str(nurse_id),
            action_type=AuditActionType.case_decision,
            details={
                "action": action,
                "reason_code": reason_code,
                "notes": notes or "",
                "new_review_status": new_status,
            },
        )

    async def log_sla_escalation(
        self,
        case_id: uuid.UUID,
        previous_queue: str,
        new_queue: str,
        entered_review_at: str,
        sla_hours: int,
    ) -> AuditLog:
        return await self._write(
            case_id=case_id,
            actor_id="sla_service",
            action_type=AuditActionType.sla_escalation,
            details={
                "previous_queue": previous_queue,
                "new_queue": new_queue,
                "entered_review_at": entered_review_at,
                "sla_hours": sla_hours,
            },
        )


# ---------------------------------------------------------------------------
# Module-level helper — opens its own session for use outside request context
# (e.g., from the SLA background scheduler)
# ---------------------------------------------------------------------------

async def log_audit_event(
    case_id: uuid.UUID,
    actor_id: str,
    action_type: AuditActionType,
    details: dict[str, Any],
) -> None:
    """
    Convenience function that opens a fresh DB session, writes one AuditLog
    row, and commits.  Intended for background tasks (e.g. sla_service) that
    run outside a FastAPI request context.

    For in-request use, prefer injecting AuditLogger(session) so the write
    participates in the request's transaction.
    """
    from src.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        try:
            row = AuditLog(
                case_id=case_id,
                actor_id=actor_id,
                action_type=action_type,
                details=details,
            )
            session.add(row)
            await session.commit()
            logger.debug(
                "AuditLog (standalone) written: case=%s action=%s actor=%s",
                case_id,
                action_type.value,
                actor_id,
            )
        except Exception:
            await session.rollback()
            logger.exception(
                "Failed to write standalone AuditLog: case=%s action=%s",
                case_id,
                action_type.value,
            )
            raise
