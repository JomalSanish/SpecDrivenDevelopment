"""initial migration

Revision ID: 1a2b3c4d5e6f
Revises: 
Create Date: 2026-07-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision: str = '1a2b3c4d5e6f'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # This is a placeholder for the initial migration.
    # We will generate this properly via `alembic revision --autogenerate` once the environment is set up.
    pass


def downgrade() -> None:
    pass
