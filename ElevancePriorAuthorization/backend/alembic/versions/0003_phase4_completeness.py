"""Phase 4 — Create completeness_report_items table.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-12

CompletenessReportItem stores the system-generated verdict (Present/Absent/Unclear)
per policy requirement per case, plus nurse override fields (CHK009).

Constitution §IV: reasoning_log preserves the full LLM prompt + response for audit.
CHK009: overridden_status/overridden_by_id/overridden_at fields added so the
        original `status` is never mutated on nurse override.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Enums ---
    op.execute(
        "CREATE TYPE completeness_status_enum AS ENUM ('Present', 'Absent', 'Unclear')"
    )
    # Separate enum type for overridden_status to allow NULL default cleanly
    op.execute(
        "CREATE TYPE completeness_override_status_enum AS ENUM ('Present', 'Absent', 'Unclear')"
    )

    # --- completeness_report_items table ---
    op.create_table(
        "completeness_report_items",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "case_id",
            UUID(as_uuid=True),
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "policy_requirement_id",
            UUID(as_uuid=True),
            sa.ForeignKey("policy_requirements.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        # System-generated verdict — NEVER mutated after creation (CHK009)
        sa.Column(
            "status",
            sa.Enum(
                "Present",
                "Absent",
                "Unclear",
                name="completeness_status_enum",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        # Auditable citation references (SEC-004) — NULL when Absent
        sa.Column("matched_document_id", UUID(as_uuid=True), nullable=True),
        sa.Column("matched_chunk_id", UUID(as_uuid=True), nullable=True),
        # Full reasoning trail (audit)
        sa.Column("reasoning_log", sa.Text(), nullable=True),
        # Nurse override fields (CHK009) — original status never touched
        sa.Column(
            "overridden_status",
            sa.Enum(
                "Present",
                "Absent",
                "Unclear",
                name="completeness_override_status_enum",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column("overridden_by_id", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "overridden_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # Indexes for common query patterns
    op.create_index(
        "ix_completeness_report_items_case_id",
        "completeness_report_items",
        ["case_id"],
    )
    op.create_index(
        "ix_completeness_report_items_policy_requirement_id",
        "completeness_report_items",
        ["policy_requirement_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_completeness_report_items_policy_requirement_id")
    op.drop_index("ix_completeness_report_items_case_id")
    op.drop_table("completeness_report_items")
    op.execute("DROP TYPE IF EXISTS completeness_override_status_enum")
    op.execute("DROP TYPE IF EXISTS completeness_status_enum")
