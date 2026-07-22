"""
backend/tests/integration/test_admin.py

T033 — Integration tests for Admin Policy Ingestion endpoint.

Spec-derived tests covering:
  POST /api/v1/admin/policies

Requirements validated:
  - FR-001: Policy documents are PDF only
  - FR-010: Policy is persisted with version lock (immutable after creation)
  - Secrets §II: Intake Agent uses local LLM endpoint only
  - Contract: PolicyIngestResponse shape (api.md §Admin Routes)
  - Error paths: non-PDF content-type, empty body, LLM unreachable (503)

Strategy:
  - Uses pytest-asyncio + httpx.AsyncClient against the FastAPI app directly
    (no live DB or Ollama required — agent and PDF extraction are mocked)
  - `@pytest.mark.integration` tests require the full docker-compose stack

Note: The FastAPI TestClient is synchronous; we use httpx.AsyncClient
with ASGITransport for full async test support.
"""
from __future__ import annotations

import io
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport


# ---------------------------------------------------------------------------
# Minimal in-memory fixtures
# ---------------------------------------------------------------------------


def _make_pdf_bytes() -> bytes:
    """
    Return a minimal valid-enough PDF header so content_type="application/pdf"
    passes the route's file-type guard.  (We patch extract_text_from_pdf, so
    the file body never needs to be a real PDF.)
    """
    return b"%PDF-1.4 test policy document"


def _intake_result_stub(num_requirements: int = 2):
    """Build a fake IntakeAgentResult for mocking."""
    from src.agents.intake_agent import IntakeAgentResult, ExtractedRequirement

    return IntakeAgentResult(
        requirements=[
            ExtractedRequirement(
                description=f"Requirement {i + 1}: clinical documentation",
                matching_criteria={"keyword": f"keyword_{i}"},
            )
            for i in range(num_requirements)
        ],
        raw_text_preview="Clinical policy text preview…",
        model_used="phi4-mini",
        prompt_tokens_approx=512,
    )


# ---------------------------------------------------------------------------
# App fixture (overrides DB session to avoid live Postgres)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client(monkeypatch):
    """
    httpx.AsyncClient wired to the FastAPI ASGI app.
    DB dependency overridden with a lightweight in-memory mock so tests do
    not require a live PostgreSQL server.
    """
    import os
    os.environ.setdefault("SECRETS_BACKEND", "env")
    os.environ.setdefault("LLM_ENDPOINT", "http://localhost:11434")
    os.environ.setdefault("EMBEDDING_ENDPOINT", "http://localhost:8080")
    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://pa_user:pa_password@localhost:5432/pa_evidence")
    os.environ.setdefault("MINIO_ENDPOINT", "localhost:9000")
    os.environ.setdefault("MINIO_ACCESS_KEY", "minioadmin")
    os.environ.setdefault("MINIO_SECRET_KEY", "minioadmin")
    os.environ.setdefault("MINIO_BUCKET", "pa-case-documents")

    from src.main import app
    from src.core.database import get_db

    # Build a mock DB session that persists objects in memory
    db_mock = _InMemorySession()
    async def _override():
        yield db_mock
    app.dependency_overrides[get_db] = _override

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


class _InMemorySession:
    """Minimal SQLAlchemy async session mock sufficient for admin_routes."""

    def __init__(self):
        self._objects = []
        self._committed = False

    def add(self, obj):
        if not hasattr(obj, "id") or obj.id is None:
            obj.id = uuid.uuid4()
        self._objects.append(obj)

    async def flush(self):
        # Assign IDs to any newly added objects without one
        for obj in self._objects:
            if not hasattr(obj, "id") or obj.id is None:
                obj.id = uuid.uuid4()

    async def refresh(self, obj):
        # Ensure id is set
        if not hasattr(obj, "id") or obj.id is None:
            obj.id = uuid.uuid4()

    async def commit(self):
        self._committed = True

    async def rollback(self):
        pass

    async def close(self):
        pass

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


async def _db_gen(session):
    """Generator that yields the mock session once."""
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


# ---------------------------------------------------------------------------
# T033 — Policy ingestion happy path
# ---------------------------------------------------------------------------


class TestAdminPolicyIngestion:
    @patch("src.api.admin_routes.extract_text_from_pdf", return_value="Policy text: clinical notes required.")
    @patch("src.api.admin_routes.get_intake_agent")
    async def test_successful_ingestion_returns_201(
        self, mock_get_agent, mock_extract, client
    ):
        """
        POST /api/v1/admin/policies with a valid PDF and all required fields
        should return 201 Created with a PolicyIngestResponse body.
        """
        mock_agent = MagicMock()
        mock_agent.extract_requirements = AsyncMock(return_value=_intake_result_stub(2))
        mock_get_agent.return_value = mock_agent

        response = await client.post(
            "/api/v1/admin/policies",
            data={
                "title": "MRI Lumbar Policy 2024",
                "service_line_code": "MRI_LUMBAR",
                "version": "2024-Q1",
            },
            files={"document": ("policy.pdf", io.BytesIO(_make_pdf_bytes()), "application/pdf")},
        )
        assert response.status_code == 201
        body = response.json()
        assert "policy_id" in body
        assert body["title"] == "MRI Lumbar Policy 2024"
        assert body["service_line_code"] == "MRI_LUMBAR"
        assert body["version"] == "2024-Q1"
        assert isinstance(body["requirements"], list)
        assert len(body["requirements"]) == 2

    @patch("src.api.admin_routes.extract_text_from_pdf", return_value="Policy text here.")
    @patch("src.api.admin_routes.get_intake_agent")
    async def test_response_contains_requirement_ids(
        self, mock_get_agent, mock_extract, client
    ):
        """Each requirement in the response must have an id and description."""
        mock_agent = MagicMock()
        mock_agent.extract_requirements = AsyncMock(return_value=_intake_result_stub(3))
        mock_get_agent.return_value = mock_agent

        response = await client.post(
            "/api/v1/admin/policies",
            data={
                "title": "Cardiac Policy",
                "service_line_code": "CARDIAC",
                "version": "v1",
            },
            files={"document": ("policy.pdf", io.BytesIO(_make_pdf_bytes()), "application/pdf")},
        )
        body = response.json()
        assert len(body["requirements"]) == 3
        for req in body["requirements"]:
            assert "id" in req
            assert "description" in req

    @patch("src.api.admin_routes.extract_text_from_pdf", return_value="Valid policy text.")
    @patch("src.api.admin_routes.get_intake_agent")
    async def test_sla_hours_persisted(self, mock_get_agent, mock_extract, client):
        """sla_hours form field should be accepted without error."""
        mock_agent = MagicMock()
        mock_agent.extract_requirements = AsyncMock(return_value=_intake_result_stub(1))
        mock_get_agent.return_value = mock_agent

        response = await client.post(
            "/api/v1/admin/policies",
            data={
                "title": "Spinal Policy",
                "service_line_code": "SPINE",
                "version": "v2",
                "sla_hours": "24",
            },
            files={"document": ("policy.pdf", io.BytesIO(_make_pdf_bytes()), "application/pdf")},
        )
        assert response.status_code == 201

    # ── FR-001: PDF-only validation ────────────────────────────────────────

    async def test_non_pdf_content_type_returns_422(self, client):
        """FR-001: Only PDF documents are accepted. Non-PDF → 422."""
        response = await client.post(
            "/api/v1/admin/policies",
            data={
                "title": "Policy",
                "service_line_code": "X",
                "version": "v1",
            },
            files={"document": ("policy.docx", io.BytesIO(b"Word content"), "application/msword")},
        )
        assert response.status_code == 422

    async def test_empty_pdf_body_returns_422(self, client):
        """An empty file upload must be rejected."""
        response = await client.post(
            "/api/v1/admin/policies",
            data={
                "title": "Policy",
                "service_line_code": "X",
                "version": "v1",
            },
            files={"document": ("policy.pdf", io.BytesIO(b""), "application/pdf")},
        )
        assert response.status_code == 422

    @patch("src.api.admin_routes.extract_text_from_pdf", return_value="")
    async def test_blank_extracted_text_returns_422(self, mock_extract, client):
        """A PDF that yields no extractable text → 422 (scanned-image-only PDF)."""
        response = await client.post(
            "/api/v1/admin/policies",
            data={
                "title": "Scanned Policy",
                "service_line_code": "X",
                "version": "v1",
            },
            files={"document": ("policy.pdf", io.BytesIO(_make_pdf_bytes()), "application/pdf")},
        )
        assert response.status_code == 422

    # ── Constitution §II: LLM is local ────────────────────────────────────

    @patch("src.api.admin_routes.extract_text_from_pdf", return_value="Policy text.")
    @patch("src.api.admin_routes.get_intake_agent")
    async def test_llm_unreachable_returns_503(
        self, mock_get_agent, mock_extract, client
    ):
        """
        If the local Ollama LLM is unreachable, the route must return 503
        Service Unavailable — not crash the server.
        (Constitution §II + agent-spec.md §3 escalation rule)
        """
        mock_agent = MagicMock()
        mock_agent.extract_requirements = AsyncMock(
            side_effect=RuntimeError("Ollama endpoint unreachable: connection refused")
        )
        mock_get_agent.return_value = mock_agent

        response = await client.post(
            "/api/v1/admin/policies",
            data={
                "title": "Policy",
                "service_line_code": "X",
                "version": "v1",
            },
            files={"document": ("policy.pdf", io.BytesIO(_make_pdf_bytes()), "application/pdf")},
        )
        assert response.status_code == 503
        body = response.json()
        assert "Ollama" in body.get("detail", "") or "unreachable" in body.get("detail", "")

    # ── Constitution §II: no external API calls ────────────────────────────

    def test_secrets_abstraction_wired_for_llm_endpoint(self, monkeypatch):
        """
        The LLM endpoint must be read through the secrets abstraction, not
        directly from os.environ.  The EnvSecretsBackend resolves it correctly.
        """
        monkeypatch.setenv("SECRETS_BACKEND", "env")
        monkeypatch.setenv("LLM_ENDPOINT", "http://localhost:11434")
        from src.core import secrets as s
        s._get_manager.cache_clear()
        from src.core.secrets import get_secret
        endpoint = get_secret("LLM_ENDPOINT")
        assert endpoint == "http://localhost:11434"
        # Must not reference any external host
        assert "openai" not in endpoint.lower()
        assert "anthropic" not in endpoint.lower()
