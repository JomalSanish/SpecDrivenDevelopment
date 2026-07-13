"""Phase 6 — Create audit_logs table.

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-13

AuditLog stores an immutable, append-only compliance trail for every
auditable event: LLM completions, RAG retrievals, nurse decisions,
checklist overrides (CHK009), case claims, SLA escalations, and policy
ingestions.

Constitution §IV: Full prompt + response captured for every LLM call.
data-model.md: action_type is a constrained Enum (not free-text String).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID, ENUM as PgEnum
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Enum for action_type ---
    # DROP IF EXISTS guard makes this safely re-runnable after a partial failure.
    op.execute("DROP TYPE IF EXISTS audit_action_type_enum")
    op.execute("""
        CREATE TYPE audit_action_type_enum AS ENUM (
            'policy_ingested',
            'case_submitted',
            'rag_retrieval',
            'llm_completion',
            'checklist_override',
            'case_claimed',
            'case_decision',
            'sla_escalation'
        )
    """)

    # --- audit_logs table ---
    op.create_table(
        "audit_logs",
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
        ),
        sa.Column("actor_id", sa.String(256), nullable=False),
        sa.Column(
            "action_type",
            PgEnum(
                "policy_ingested",
                "case_submitted",
                "rag_retrieval",
                "llm_completion",
                "checklist_override",
                "case_claimed",
                "case_decision",
                "sla_escalation",
                name="audit_action_type_enum",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("details", JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # Indexes for common query patterns
    op.create_index("ix_audit_logs_case_id", "audit_logs", ["case_id"])
    op.create_index("ix_audit_logs_actor_id", "audit_logs", ["actor_id"])
    op.create_index("ix_audit_logs_action_type", "audit_logs", ["action_type"])
    op.create_index("ix_audit_logs_timestamp", "audit_logs", ["timestamp"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_timestamp")
    op.drop_index("ix_audit_logs_action_type")
    op.drop_index("ix_audit_logs_actor_id")
    op.drop_index("ix_audit_logs_case_id")
    op.drop_table("audit_logs")
    op.execute("DROP TYPE IF EXISTS audit_action_type_enum")
