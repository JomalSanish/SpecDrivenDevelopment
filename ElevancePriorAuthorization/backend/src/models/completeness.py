"""
backend/src/models/completeness.py

CompletenessReportItem ORM model — T018.

Matches data-model.md exactly:
  - status: system-generated classification (Present/Absent/Unclear)
  - confidence_score: float from the reasoning LLM
  - matched_document_id / matched_chunk_id: stable UUIDs for auditable citations (SEC-004)
  - overridden_status / overridden_by_id / overridden_at: nurse override fields (CHK009)
    The original `status` is NEVER mutated on override; only overridden_status is set,
    so the original agent output remains reconstructable.

Constitution §IV: Every completeness assessment is auditable via reasoning_log.
Constitution §I:  No automated accept/reject — status is Present/Absent/Unclear only.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, Float, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.core import Base


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class CompletenessStatus(str, enum.Enum):
    """
    System-generated (original) completeness classification.

    Thresholds enforced by the Reasoning Agent (T020):
      Present : confidence > 0.80
      Unclear : 0.50 <= confidence <= 0.80
      Absent  : confidence < 0.50

    For identifier-based requirements (member ID, CPT, HCPCS, ICD-10),
    a keyword_miss flag from the Retrieval Agent forces Unclear regardless
    of the dense confidence score.
    """

    Present = "Present"
    Absent = "Absent"
    Unclear = "Unclear"


# ---------------------------------------------------------------------------
# CompletenessReportItem
# ---------------------------------------------------------------------------


class CompletenessReportItem(Base):
    """
    One line-item of the completeness report for a case.

    Each item maps a single PolicyRequirement to its evidence verdict for
    a given case.  The system-generated `status` is immutable after creation;
    a nurse may record a manual override in `overridden_status` (CHK009).

    `matched_document_id` and `matched_chunk_id` are stable UUID references
    to the evidence chunk that most strongly supported the verdict (SEC-004).
    Either may be NULL when status is Absent (no evidence found).
    """

    __tablename__ = "completeness_report_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    policy_requirement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("policy_requirements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # System-generated verdict — NEVER mutated after creation (CHK009)
    status: Mapped[CompletenessStatus] = mapped_column(
        SAEnum(CompletenessStatus, name="completeness_status_enum", create_type=False),
        nullable=False,
    )
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)

    # Auditable citation fields (SEC-004) — NULL when Absent
    matched_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    matched_chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    # Full reasoning trail for audit reconstruction
    reasoning_log: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Nurse override fields (CHK009) — original `status` left untouched
    overridden_status: Mapped[CompletenessStatus | None] = mapped_column(
        SAEnum(
            CompletenessStatus,
            name="completeness_override_status_enum",
            create_type=False,
        ),
        nullable=True,
    )
    overridden_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    overridden_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<CompletenessReportItem id={self.id} case_id={self.case_id} "
            f"req_id={self.policy_requirement_id} status={self.status} "
            f"confidence={self.confidence_score:.2f}>"
        )
