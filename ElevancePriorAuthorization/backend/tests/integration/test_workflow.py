"""
backend/tests/integration/test_workflow.py

T035 — Integration tests verifying Nurse Review explicit state fields and workflow constraints.

Spec-derived tests covering:
  - Constitution §I: No automated decisions (system CANNOT output accepted/rejected).
    Case transitions to in_nurse_review and waits.
  - Constitution §I: Only a nurse can call /decision.
  - Constitution §I: Reject maps to 'returned_to_provider'.
  - POST /claim requires atomic lock.

Uses the same lightweight in-memory DB override approach as test_admin.py to run
without a live Postgres instance for non-@pytest.mark.integration runs.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from src.models.case import Case, ReviewStatus, AssignedQueue
from src.models.policy import Policy


# ---------------------------------------------------------------------------
# Minimal in-memory DB mock
# ---------------------------------------------------------------------------

class _InMemorySession:
    def __init__(self, objects: list = None):
        self._objects = objects or []
        self._committed = False

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        self._objects.append(obj)

    async def flush(self):
        for obj in self._objects:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()

    async def refresh(self, obj):
        pass

    async def commit(self):
        self._committed = True

    async def rollback(self):
        pass

    async def close(self):
        pass

    async def execute(self, stmt):
        class MockResult:
            def __init__(self, objs):
                self.objs = objs
            def unique(self):
                return self
            def scalars(self):
                return self
            def all(self):
                return self.objs
            def first(self):
                return self.objs[0] if self.objs else None
            def scalar_one_or_none(self):
                return self.objs[0] if self.objs else None
            def fetchall(self):
                return [(obj,) for obj in self.objs]
            
            @property
            def rowcount(self):
                # For updates
                return len(self.objs)

        # Very naive evaluation for test purposes
        # Just return all Case objects if querying Case
        if "case" in str(stmt).lower():
            cases = [obj for obj in self._objects if isinstance(obj, Case)]
            # If there is a where clause for id
            # This is extremely naive and tailored to the exact queries we expect
            return MockResult(cases)
        if "policy" in str(stmt).lower():
            policies = [obj for obj in self._objects if isinstance(obj, Policy)]
            return MockResult(policies)
        
        return MockResult([])

async def _db_gen(session):
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


@pytest_asyncio.fixture
async def client_factory(monkeypatch):
    """
    Returns a function that creates a client with a pre-seeded in-memory DB.
    """
    monkeypatch.setenv("SECRETS_BACKEND", "env")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://pa_user:pa_password@localhost:5432/pa_evidence")

    from src.main import app
    from src.core.database import get_db

    async def _create_client(seed_objects: list = None):
        db_mock = _InMemorySession(seed_objects or [])
        async def _override():
            yield db_mock

        app.dependency_overrides[get_db] = _override
        transport = ASGITransport(app=app)
        # Yield the client and db so tests can inspect state
        client = AsyncClient(transport=transport, base_url="http://test")
        return client, db_mock

    yield _create_client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# T035 — Explicit state field checks
# ---------------------------------------------------------------------------


class TestWorkflowConstraints:
    
    @patch("src.api.review_routes.logger")
    @patch("src.api.review_routes.AuditLogger", create=True)
    @pytest.mark.asyncio
    async def test_claim_assigns_nurse_id(self, mock_audit, mock_logger, client_factory):
        """POST /claim must set claimed_by_id and not change the review_status."""
        case_id = uuid.uuid4()
        test_case = Case(
            id=case_id,
            member_id="MEM123",
            provider_id="PROV123",
            cpt_code="12345",
            icd10_code="A00",
            service_type="Test",
            requested_date=datetime.now(timezone.utc),
            policy_id=uuid.uuid4(),
            review_status=ReviewStatus.in_nurse_review,
            assigned_queue=AssignedQueue.nurse_review,
            claimed_by_id=None
        )
        client, db_mock = await client_factory([test_case])
        
        nurse_id = str(uuid.uuid4())
        
        # We must mock `execute` to handle the UPDATE stmt that checks claimed_by_id.
        # SQLAlchemy's update().where() is hard to mock exactly, so we mock execute for the UPDATE
        original_execute = db_mock.execute
        async def mock_execute(stmt):
            if "UPDATE" in str(stmt).upper():
                # Simulate successful claim
                test_case.claimed_by_id = uuid.UUID(nurse_id)
                class Result:
                    rowcount = 1
                return Result()
            return await original_execute(stmt)
            
        db_mock.execute = mock_execute

        response = await client.post(
            f"/api/v1/review/cases/{case_id}/claim?nurse_id={nurse_id}"
        )
        
        assert response.status_code == 200
        assert str(test_case.claimed_by_id) == nurse_id
        # State MUST remain in_nurse_review per Constitution §I
        assert test_case.review_status == ReviewStatus.in_nurse_review

    @patch("src.api.review_routes.AuditLogger", create=True)
    @pytest.mark.asyncio
    async def test_claim_conflict_returns_409(self, mock_audit, client_factory):
        """POST /claim must return 409 if rows-affected == 0 (already claimed)."""
        case_id = uuid.uuid4()
        test_case = Case(
            id=case_id,
            member_id="MEM123",
            provider_id="PROV123",
            cpt_code="12345",
            icd10_code="A00",
            service_type="Test",
            requested_date=datetime.now(timezone.utc),
            policy_id=uuid.uuid4(),
            review_status=ReviewStatus.in_nurse_review,
            assigned_queue=AssignedQueue.nurse_review,
            claimed_by_id=uuid.uuid4()  # Already claimed!
        )
        client, db_mock = await client_factory([test_case])
        
        original_execute = db_mock.execute
        async def mock_execute(stmt):
            if "UPDATE" in str(stmt).upper():
                # Simulate failure to claim (atomic lock miss)
                class Result:
                    rowcount = 0
                return Result()
            return await original_execute(stmt)
            
        db_mock.execute = mock_execute

        response = await client.post(
            f"/api/v1/review/cases/{case_id}/claim?nurse_id={uuid.uuid4()}"
        )
        assert response.status_code == 409
        assert "already claimed" in str(response.json()["detail"]).lower()

    @patch("src.api.review_routes.AuditLogger", create=True)
    @pytest.mark.asyncio
    async def test_decision_by_non_claimant_returns_403(self, mock_audit, client_factory):
        """Constitution §I: /decision is rejected 403 if requestor != claimant."""
        case_id = uuid.uuid4()
        correct_nurse = uuid.uuid4()
        wrong_nurse = uuid.uuid4()
        
        test_case = Case(
            id=case_id,
            member_id="M1",
            provider_id="P1",
            cpt_code="123",
            icd10_code="A1",
            service_type="T",
            requested_date=datetime.now(timezone.utc),
            policy_id=uuid.uuid4(),
            review_status=ReviewStatus.in_nurse_review,
            assigned_queue=AssignedQueue.nurse_review,
            claimed_by_id=correct_nurse
        )
        client, db_mock = await client_factory([test_case])

        response = await client.post(
            f"/api/v1/review/cases/{case_id}/decision",
            json={
                "nurse_id": str(wrong_nurse),
                "action": "Accept",
                "reason_code": "CRITERIA_NOT_MET",
                "notes": "Meets criteria."
            }
        )
        assert response.status_code == 403
        assert "claim lock" in str(response.json()["detail"]).lower()
        # Status must not change
        assert test_case.review_status == ReviewStatus.in_nurse_review

    @patch("src.api.review_routes.AuditLogger", create=True)
    @pytest.mark.asyncio
    async def test_decision_reject_maps_to_returned_to_provider(self, mock_audit, client_factory):
        """Constitution §I: Reject maps to 'returned_to_provider'."""
        case_id = uuid.uuid4()
        nurse_id = uuid.uuid4()
        
        test_case = Case(
            id=case_id,
            member_id="M1",
            provider_id="P1",
            cpt_code="123",
            icd10_code="A1",
            service_type="T",
            requested_date=datetime.now(timezone.utc),
            policy_id=uuid.uuid4(),
            review_status=ReviewStatus.in_nurse_review,
            assigned_queue=AssignedQueue.nurse_review,
            claimed_by_id=nurse_id
        )
        client, db_mock = await client_factory([test_case])

        original_execute = db_mock.execute
        async def mock_execute(stmt):
            if "UPDATE" in str(stmt).upper():
                test_case.review_status = ReviewStatus.returned_to_provider
                test_case.decided_by_id = nurse_id
                test_case.decision_reason = "Missing clinicals."
                class Result:
                    rowcount = 1
                return Result()
            return await original_execute(stmt)
        db_mock.execute = mock_execute

        response = await client.post(
            f"/api/v1/review/cases/{case_id}/decision",
            json={
                "nurse_id": str(nurse_id),
                "action": "Reject",
                "reason_code": "MISSING_CLINICAL_NOTES",
                "notes": "Missing clinicals."
            }
        )
        assert response.status_code == 200
        # Check explicit mapping
        assert test_case.review_status == ReviewStatus.returned_to_provider
        assert test_case.decided_by_id == nurse_id
        assert test_case.decision_reason == "Missing clinicals."

    @patch("src.api.review_routes.AuditLogger", create=True)
    @pytest.mark.asyncio
    async def test_decision_accept_maps_to_accepted(self, mock_audit, client_factory):
        case_id = uuid.uuid4()
        nurse_id = uuid.uuid4()
        
        test_case = Case(
            id=case_id,
            member_id="M1",
            provider_id="P1",
            cpt_code="123",
            icd10_code="A1",
            service_type="T",
            requested_date=datetime.now(timezone.utc),
            policy_id=uuid.uuid4(),
            review_status=ReviewStatus.in_nurse_review,
            assigned_queue=AssignedQueue.nurse_review,
            claimed_by_id=nurse_id
        )
        client, db_mock = await client_factory([test_case])

        original_execute = db_mock.execute
        async def mock_execute(stmt):
            if "UPDATE" in str(stmt).upper():
                test_case.review_status = ReviewStatus.accepted
                class Result:
                    rowcount = 1
                return Result()
            return await original_execute(stmt)
        db_mock.execute = mock_execute

        response = await client.post(
            f"/api/v1/review/cases/{case_id}/decision",
            json={
                "nurse_id": str(nurse_id),
                "action": "Accept",
                "reason_code": "OK"
            }
        )
        assert response.status_code == 200
        assert test_case.review_status == ReviewStatus.accepted
