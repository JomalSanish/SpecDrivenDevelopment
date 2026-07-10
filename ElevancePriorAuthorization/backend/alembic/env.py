"""
backend/alembic/env.py
Alembic environment — resolves the DB URL from the secrets abstraction,
not from a plain environment variable.
"""
import sys
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Add backend/ to path so src.* imports resolve
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.secrets import get_secret  # noqa: E402
from src.models.core import Base  # noqa: E402
# Import all models so Alembic detects them for autogenerate
import src.models  # noqa: F401, E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Resolve DB URL via secrets abstraction — no plain env var access here
database_url = get_secret("DATABASE_URL")
# asyncpg URLs are not usable with sync Alembic engine; swap driver
sync_url = database_url.replace("postgresql+asyncpg://", "postgresql://")
config.set_main_option("sqlalchemy.url", sync_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
