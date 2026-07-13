"""
backend/src/models/audit.py

AuditLog ORM model — T028.

Matches data-model.md exactly:
  - action_type: constrained Enum (not free-text) so every traced event
    is queryable and reportable (CHK009, SEC-004, Constitution §IV).
  - details: JSONB — carries prompts, chunk IDs, confidence scores, and
    for checklist_override MUST include:
      completeness_report_item_id, original_status, new_status
  - actor_id: String (system agent name OR human UUID string) — supports
    both agent-level and nurse-level attribution.

Constitution §IV: Every RAG retrieval, LLM completion, nurse decision,
    checklist override, SLA escalation, and policy ingestion writes a row
    here so the full audit trail is reconstructable from the database alone.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.core import Base


# ---------------------------------------------------------------------------
# Action type enumeration (constrained — not free-text)
# ---------------------------------------------------------------------------


class AuditActionType(str, enum.Enum):
    """
    Constrained set of audit action types (data-model.md).

    Using a database-level Enum (not free-text String) ensures:
      1. Every event is queryable by type without full-text search.
      2. Typos cannot create invisible audit holes.
      3. checklist_override is first-class (CHK009).
      4. SLA escalations are traceable independently.
    """

    policy_ingested = "policy_ingested"
    case_submitted = "case_submitted"
    rag_retrieval = "rag_retrieval"
    llm_completion = "llm_completion"
    checklist_override = "checklist_override"
    case_claimed = "case_claimed"
    case_decision = "case_decision"
    sla_escalation = "sla_escalation"


# ---------------------------------------------------------------------------
# AuditLog
# ---------------------------------------------------------------------------


class AuditLog(Base):
    """
    Immutable, append-only audit record.

    One row per discrete auditable event. Rows are never updated or deleted —
    this provides a tamper-evident compliance trail (Constitution §IV).

    actor_id : str
        For system events: agent name (e.g. "intake_agent", "reasoning_agent").
        For human events:  the nurse/admin UUID as a string.

    details  : dict  (JSONB)
        Free-form JSON payload. Mandatory keys by action_type:
          llm_completion      → {prompt, model, response_excerpt}
          rag_retrieval       → {query, chunk_ids, scores, case_id}
          checklist_override  → {completeness_report_item_id,
                                  original_status, new_status}
          case_decision       → {action, reason_code, notes}
          case_claimed        → {nurse_id}
          sla_escalation      → {previous_queue, new_queue,
                                  entered_review_at, sla_hours}
    """

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_id: Mapped[str] = mapped_column(
        String(256), nullable=False, index=True
    )
    action_type: Mapped[AuditActionType] = mapped_column(
        SAEnum(AuditActionType, name="audit_action_type_enum", create_type=True),
        nullable=False,
        index=True,
    )
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    def __repr__(self) -> str:
        return (
            f"<AuditLog id={self.id} case={self.case_id} "
            f"type={self.action_type} actor={self.actor_id}>"
        )
