"""
backend/src/models/__init__.py

Import all ORM models here so that Alembic's env.py (which does
`import src.models`) discovers every table via Base.metadata.
"""
# noqa: F401
from src.models import audit, case, completeness, policy  # type: ignore[import]
