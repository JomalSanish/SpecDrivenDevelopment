"""
backend/tests/conftest.py
Shared pytest fixtures for all backend tests.
"""
import os
import sys
import pytest

# Ensure backend/src is on the path so tests resolve imports correctly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Force env backend for all tests — no Vault required in CI
os.environ.setdefault("SECRETS_BACKEND", "env")
os.environ.setdefault("LLM_ENDPOINT", "http://localhost:11434")
os.environ.setdefault("EMBEDDING_ENDPOINT", "http://localhost:8080")
os.environ.setdefault("QDRANT_HOST", "localhost")
os.environ.setdefault("QDRANT_PORT", "6333")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://pa_user:pa_password@localhost:5432/pa_evidence")
os.environ.setdefault("MINIO_ACCESS_KEY", "minioadmin")
os.environ.setdefault("MINIO_SECRET_KEY", "minioadmin")
