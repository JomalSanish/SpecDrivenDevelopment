import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import event, DDL

DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql://postgres:password@localhost:5432/prior_auth"
)

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# T004a [FR-017] Implement Postgres table partitioning for audit logs
# This will be attached to the metadata creation event to ensure the partitioned table is set up.
# We will create a trigger/function or just rely on Postgres declarative partitioning.
# Since SQLAlchemy's declarative base doesn't natively support declarative partitioning perfectly,
# we define the SQL manually here to be executed after table creation, or manage it via Alembic.

def setup_partitioning(target, connection, **kw):
    """
    Setup declarative partitioning for audit logs based on timestamp.
    Assumes the base table `audit_logs` is created as a PARTITIONED TABLE.
    """
    # Note: Alembic or raw SQL is better for this. In SQLAlchemy we can just execute DDL.
    # Since we can't easily do `CREATE TABLE ... PARTITION BY RANGE` in basic SQLAlchemy Base,
    # we'll execute DDL for partitions.
    
    # We will assume audit_logs is created normally, but if we need native Postgres partitioning,
    # we actually need to change the CREATE TABLE statement.
    pass

# We will handle the actual partitioning in the Alembic migration or by executing raw SQL 
# since SQLAlchemy Base doesn't support declarative partitioning out of the box.

