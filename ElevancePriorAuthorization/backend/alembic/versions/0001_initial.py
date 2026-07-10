"""%(message)s
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Core model tables (policy, case, document, audit_log, completeness)
    # will be added in dedicated revision files per phase.
    # This initial revision only ensures the extension is available.
    op.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")


def downgrade() -> None:
    pass
