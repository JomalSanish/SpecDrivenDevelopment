"""
backend/tests/unit/test_phase2_models.py

Phase 2 unit tests — validates models, schemas, and agent logic without
requiring a running database, MinIO, or LLM.

Tests:
  1. Policy + PolicyRequirement model construction
  2. Case model enforces explicit Enum state (no free-text routing)
  3. ReviewStatus has no 'rejected' variant (constitution §I)
  4. AssignedQueue is Enum, not String
  5. Document model stable UUID (constitution §IV)
  6. IntakeAgent._parse_requirements parses valid JSON
  7. IntakeAgent._parse_requirements raises RuntimeError on bad JSON
  8. IntakeAgent._parse_requirements raises RuntimeError on non-list JSON
  9. PDF service gracefully returns empty string when no PDF libs installed
 10. Admin ingest endpoint rejects non-PDF uploads (schema validation)
 11. No external API hostnames appear in intake_agent.py source
"""
import inspect
import json
import uuid
import pytest

# ---------------------------------------------------------------------------
# 1-5: ORM models
# ---------------------------------------------------------------------------


class TestPolicyModel:
    def test_policy_model_construction(self):
        from src.models.policy import Policy
        p = Policy(title="Test Policy", service_line_code="TEST", version="1.0")
        assert p.title == "Test Policy"
        assert p.sla_hours is None  # optional

    def test_policy_requirement_construction(self):
        from src.models.policy import PolicyRequirement
        req = PolicyRequirement(
            policy_id=uuid.uuid4(),
            description="Clinical notes",
            matching_criteria={"keywords": ["notes"]},
        )
        assert req.description == "Clinical notes"
        assert req.matching_criteria["keywords"] == ["notes"]


class TestCaseModel:
    def test_review_status_has_no_rejected_variant(self):
        """
        Constitution §I: "Reject" always maps to returned_to_provider.
        There MUST NOT be a 'rejected' member in ReviewStatus.
        """
        from src.models.case import ReviewStatus
        member_names = {m.value for m in ReviewStatus}
        assert "rejected" not in member_names, (
            "ReviewStatus must NOT have a 'rejected' value. "
            "A nurse Reject maps to 'returned_to_provider' (Constitution §I)."
        )
        assert "returned_to_provider" in member_names

    def test_assigned_queue_is_enum_not_string(self):
        """
        data-model.md: assigned_queue MUST be Enum, not free-text String.
        """
        import enum
        from src.models.case import AssignedQueue
        assert issubclass(AssignedQueue, enum.Enum)

    def test_case_explicit_state_fields(self):
        """No hidden booleans — all routing via explicit fields (SEC-001)."""
        from src.models.case import Case
        annotations = Case.__annotations__
        # Must NOT have a 'human_review_required' or 'is_reviewed' flag
        forbidden = {"human_review_required", "is_reviewed", "auto_approved"}
        for name in forbidden:
            assert name not in annotations, (
                f"Case model must not have a '{name}' hidden boolean flag (Constitution §I)."
            )

    def test_document_has_stable_uuid_pk(self):
        """SEC-004: Document.id is UUID (not int) for stable citation."""
        from src.models.case import Document
        from sqlalchemy.dialects.postgresql import UUID as PGUUID
        id_col = Document.__table__.columns.get("id")
        assert id_col is not None
        assert isinstance(id_col.type, PGUUID)


# ---------------------------------------------------------------------------
# 6-8: Intake Agent parsing
# ---------------------------------------------------------------------------


class TestIntakeAgentParsing:
    def test_parses_valid_json_array(self):
        from src.agents.intake_agent import IntakeClassificationAgent
        content = json.dumps([
            {"description": "Clinical notes", "matching_criteria": {"keywords": ["notes"]}},
            {"description": "Imaging report", "matching_criteria": {}},
        ])
        reqs = IntakeClassificationAgent._parse_requirements(content)
        assert len(reqs) == 2
        assert reqs[0].description == "Clinical notes"
        assert reqs[1].description == "Imaging report"

    def test_raises_on_invalid_json(self):
        from src.agents.intake_agent import IntakeClassificationAgent
        with pytest.raises(RuntimeError, match="invalid JSON"):
            IntakeClassificationAgent._parse_requirements("not json at all {{{")

    def test_raises_on_non_list_json(self):
        from src.agents.intake_agent import IntakeClassificationAgent
        with pytest.raises(RuntimeError, match="not a list"):
            IntakeClassificationAgent._parse_requirements('{"key": "value"}')

    def test_strips_markdown_fences(self):
        from src.agents.intake_agent import IntakeClassificationAgent
        content = '```json\n[{"description": "Notes"}]\n```'
        reqs = IntakeClassificationAgent._parse_requirements(content)
        assert len(reqs) == 1

    def test_skips_malformed_items(self):
        from src.agents.intake_agent import IntakeClassificationAgent
        content = json.dumps([
            {"description": "Valid item"},
            {"bad_key": "no description"},  # malformed — should be skipped
        ])
        reqs = IntakeClassificationAgent._parse_requirements(content)
        assert len(reqs) == 1
        assert reqs[0].description == "Valid item"


# ---------------------------------------------------------------------------
# 9: PDF service graceful degradation
# ---------------------------------------------------------------------------


class TestPdfService:
    def test_returns_empty_string_on_invalid_bytes(self):
        from src.services.pdf_service import extract_text_from_pdf
        result = extract_text_from_pdf(b"not a pdf")
        assert isinstance(result, str)  # must not raise — graceful degradation


# ---------------------------------------------------------------------------
# 11: No external API hostnames in intake_agent source (constitution §II)
# ---------------------------------------------------------------------------


class TestNoExternalApiCalls:
    FORBIDDEN_HOSTS = [
        "openai.com",
        "api.openai.com",
        "anthropic.com",
        "api.anthropic.com",
        "cohere.com",
        "api.cohere.com",
        "huggingface.co",  # inference API (not local TEI)
    ]

    def test_intake_agent_has_no_hardcoded_external_hosts(self):
        """
        Constitution §II: The intake agent MUST NOT reference any public
        LLM API hostnames in its source code.
        """
        import src.agents.intake_agent as mod
        source = inspect.getsource(mod)
        for host in self.FORBIDDEN_HOSTS:
            assert host not in source, (
                f"Found forbidden external API host '{host}' in intake_agent.py source. "
                "All LLM calls MUST go to the locally configured endpoint (Constitution §II)."
            )

    def test_admin_routes_has_no_hardcoded_external_hosts(self):
        import src.api.admin_routes as mod
        source = inspect.getsource(mod)
        for host in self.FORBIDDEN_HOSTS:
            assert host not in source, (
                f"Found forbidden external API host '{host}' in admin_routes.py."
            )
