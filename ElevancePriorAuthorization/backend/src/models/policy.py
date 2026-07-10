"""
backend/src/models/policy.py

Policy and PolicyRequirement ORM models.
Matches data-model.md exactly.

Constitution §V: No credentials here; all DB access goes through the secrets layer.
Constitution §I:  Policy version is locked at case submission (FR-010) — the
                  policy row must never be mutated once a case references it;
                  updates create a new version.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Integer, String, Text, ForeignKey, DateTime, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.core import Base


class Policy(Base):
    """
    Represents a payer policy document.

    sla_hours — optional SLA duration (hours) for nurse review of cases
    against this policy.  Falls back to the system-wide default when NULL.
    (Used by the SLA escalation service in Phase 6 / T031.)
    """

    __tablename__ = "policies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    service_line_code: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sla_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    requirements: Mapped[list["PolicyRequirement"]] = relationship(
        "PolicyRequirement", back_populates="policy", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Policy id={self.id} title={self.title!r} version={self.version}>"


class PolicyRequirement(Base):
    """
    A single required evidence item extracted from a Policy document.

    matching_criteria — JSON instructions used by the RAG Reasoning Agent
    when evaluating whether a case document satisfies this requirement.
    """

    __tablename__ = "policy_requirements"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    policy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("policies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    description: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # e.g. "Clinical notes from last 6 months"
    matching_criteria: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )  # JSON instructions for RAG reasoning

    # Relationships
    policy: Mapped["Policy"] = relationship("Policy", back_populates="requirements")

    def __repr__(self) -> str:
        return (
            f"<PolicyRequirement id={self.id} "
            f"policy_id={self.policy_id} desc={self.description[:40]!r}>"
        )
