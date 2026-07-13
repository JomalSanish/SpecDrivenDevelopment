"""
backend/src/models/case.py

Case and Document ORM models.
Matches data-model.md exactly.

Critical constitution constraints enforced here:
  §I  — No hidden booleans. Explicit state fields only:
        review_status, assigned_queue, claimed_by_id, decided_by_id, decision_at.
  §I  — "Reject" maps to 'returned_to_provider', NOT a separate 'rejected' state.
  §I  — assigned_queue is an Enum (not free-text String) to prevent typo-routing.
  §I  — entered_review_at is set when review_status first becomes 'in_nurse_review'.
        SLA escalation (T031) measures from this timestamp, NOT from claimed_by_id,
        so an unclaimed case can still breach SLA and escalate.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.core import Base


# ---------------------------------------------------------------------------
# Enumerations (explicit state — constitution §I)
# ---------------------------------------------------------------------------


class ReviewStatus(str, enum.Enum):
    """
    Explicit review lifecycle states.

    Note: There is no 'rejected' value — a nurse's Reject action always
    means the case is returned to the provider for more documentation.
    It maps to 'returned_to_provider'. This is intentional and mandated
    by the constitution to prevent terminal-denial confusion.
    """

    pending_verification = "pending_verification"
    in_nurse_review = "in_nurse_review"
    accepted = "accepted"
    returned_to_provider = "returned_to_provider"


class AssignedQueue(str, enum.Enum):
    """
    Explicit queue assignments.

    Stored as an Enum (not free-text) to prevent silent routing bugs.
    (data-model.md: assigned_queue must be an Enum, not a String.)
    """

    nurse_review = "nurse_review"
    escalation_manager = "escalation_manager"
    medical_director_review = "medical_director_review"


class DocumentType(str, enum.Enum):
    pdf = "PDF"
    scan = "Scan"
    fax = "Fax"


# ---------------------------------------------------------------------------
# Case
# ---------------------------------------------------------------------------


class Case(Base):
    """
    A prior authorization request.

    All routing uses explicit state fields (SEC-001 / constitution §I).
    The policy_id is locked at submission (FR-010).
    """

    __tablename__ = "cases"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    member_id: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_id: Mapped[str] = mapped_column(String(128), nullable=False)
    cpt_code: Mapped[str] = mapped_column(String(16), nullable=False)
    icd10_code: Mapped[str] = mapped_column(String(16), nullable=False)
    service_type: Mapped[str] = mapped_column(String(128), nullable=False)
    requested_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Policy locked at submission time (FR-010)
    policy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("policies.id"),
        nullable=False,
        index=True,
    )

    # Explicit workflow state (SEC-001 — no hidden booleans)
    review_status: Mapped[ReviewStatus] = mapped_column(
        SAEnum(ReviewStatus, name="review_status_enum", create_type=False),
        default=ReviewStatus.pending_verification,
        nullable=False,
    )
    assigned_queue: Mapped[AssignedQueue] = mapped_column(
        SAEnum(AssignedQueue, name="assigned_queue_enum", create_type=False),
        default=AssignedQueue.nurse_review,
        nullable=False,
    )

    # Strict claim lock (FR-009)
    claimed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    # SLA anchor (T031): set when status first becomes in_nurse_review
    entered_review_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Decision fields (constitution §I — explicit attribution)
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    documents: Mapped[list["Document"]] = relationship(
        "Document", back_populates="case", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<Case id={self.id} member={self.member_id} "
            f"status={self.review_status}>"
        )


# ---------------------------------------------------------------------------
# Document (case evidence file)
# ---------------------------------------------------------------------------


class Document(Base):
    """
    A single uploaded case evidence file (PDF / Scan / Fax).

    storage_path — MinIO object key used to retrieve the file.
    id is a stable UUID cited in CompletenessReportItems (SEC-004).
    """

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_type: Mapped[DocumentType] = mapped_column(
        SAEnum(
            DocumentType,
            name="document_type_enum",
            create_type=False,
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
    )
    storage_path: Mapped[str] = mapped_column(
        String(1024), nullable=False
    )  # MinIO object key
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    case: Mapped["Case"] = relationship("Case", back_populates="documents")

    def __repr__(self) -> str:
        return f"<Document id={self.id} case_id={self.case_id} type={self.document_type}>"
