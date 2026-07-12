"""Phase 2 — Create policy, policy_requirements, cases, and documents tables.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-10
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Enums ---
    op.execute(
        "CREATE TYPE review_status_enum AS ENUM "
        "('pending_verification', 'in_nurse_review', 'accepted', 'returned_to_provider')"
    )
    op.execute(
        "CREATE TYPE assigned_queue_enum AS ENUM "
        "('nurse_review', 'escalation_manager', 'medical_director_review')"
    )
    op.execute(
        "CREATE TYPE document_type_enum AS ENUM ('PDF', 'Scan', 'Fax')"
    )

    # --- policies ---
    op.create_table(
        "policies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("service_line_code", sa.String(64), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("sla_hours", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # --- policy_requirements ---
    op.create_table(
        "policy_requirements",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "policy_id",
            UUID(as_uuid=True),
            sa.ForeignKey("policies.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("matching_criteria", JSONB(), nullable=True),
    )

    # --- cases ---
    op.create_table(
        "cases",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("member_id", sa.String(128), nullable=False),
        sa.Column("provider_id", sa.String(128), nullable=False),
        sa.Column("cpt_code", sa.String(16), nullable=False),
        sa.Column("icd10_code", sa.String(16), nullable=False),
        sa.Column("service_type", sa.String(128), nullable=False),
        sa.Column("requested_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "policy_id",
            UUID(as_uuid=True),
            sa.ForeignKey("policies.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "review_status",
            sa.Enum(
                "pending_verification",
                "in_nurse_review",
                "accepted",
                "returned_to_provider",
                name="review_status_enum",
                create_type=False,  # already created above
            ),
            nullable=False,
            server_default="pending_verification",
        ),
        sa.Column(
            "assigned_queue",
            sa.Enum(
                "nurse_review",
                "escalation_manager",
                "medical_director_review",
                name="assigned_queue_enum",
                create_type=False,
            ),
            nullable=False,
            server_default="nurse_review",
        ),
        sa.Column("claimed_by_id", UUID(as_uuid=True), nullable=True),
        sa.Column("entered_review_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by_id", UUID(as_uuid=True), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("decision_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # --- documents ---
    op.create_table(
        "documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "case_id",
            UUID(as_uuid=True),
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "document_type",
            sa.Enum("PDF", "Scan", "Fax", name="document_type_enum", create_type=False),
            nullable=False,
        ),
        sa.Column("storage_path", sa.String(1024), nullable=False),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("documents")
    op.drop_table("cases")
    op.drop_table("policy_requirements")
    op.drop_table("policies")
    op.execute("DROP TYPE IF EXISTS document_type_enum")
    op.execute("DROP TYPE IF EXISTS assigned_queue_enum")
    op.execute("DROP TYPE IF EXISTS review_status_enum")
