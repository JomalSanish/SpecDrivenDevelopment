"""
backend/tests/unit/test_reasoning_agent.py

T036 — Unit tests for confidence threshold edge cases in the Reasoning Agent.

Spec-derived tests covering:
  - T020: threshold guardrails (Present / Unclear / Absent cutoffs)
  - Identifier-based + keyword_miss → forced Unclear
  - LLM parse failure → forced Unclear (NOT Absent — fail-safe)
  - Boundary values (exactly 0.80, exactly 0.50)
  - Confidence clamping (< 0, > 1)
  - _parse_llm_response happy-path and error paths

All tests are pure unit tests (no DB, no network). `apply_confidence_guardrails`
and `_parse_llm_response` are deterministic functions — no mocking required.
"""
from __future__ import annotations

import json
import pytest

# Env set in conftest.py; importing after to ensure path is correct
from src.agents.reasoning_agent import (
    THRESHOLD_PRESENT,
    THRESHOLD_UNCLEAR,
    apply_confidence_guardrails,
    _parse_llm_response,
)
from src.models.completeness import CompletenessStatus


# ---------------------------------------------------------------------------
# Sanity-check the threshold constants (spec §T020)
# ---------------------------------------------------------------------------


class TestThresholdConstants:
    def test_present_threshold_is_0_80(self):
        """Spec T020 mandates > 0.80 → Present."""
        assert THRESHOLD_PRESENT == 0.80

    def test_unclear_threshold_is_0_50(self):
        """Spec T020 mandates < 0.50 → Absent, so the Unclear floor is 0.50."""
        assert THRESHOLD_UNCLEAR == 0.50


# ---------------------------------------------------------------------------
# apply_confidence_guardrails — nominal path
# ---------------------------------------------------------------------------


class TestApplyConfidenceGuardrails:
    # ── Present ──────────────────────────────────────────────────────────────

    def test_high_confidence_is_present(self):
        """confidence > 0.80 → Present."""
        status, kw_miss = apply_confidence_guardrails(0.95, False, 0)
        assert status == CompletenessStatus.Present
        assert kw_miss is False

    def test_exactly_above_present_boundary(self):
        """confidence = 0.801 → Present (just above boundary)."""
        status, _ = apply_confidence_guardrails(0.801, False, 0)
        assert status == CompletenessStatus.Present

    # ── Unclear ───────────────────────────────────────────────────────────────

    def test_boundary_at_present_threshold_is_unclear(self):
        """confidence = exactly 0.80 → Unclear (not Present — threshold is strictly >)."""
        status, _ = apply_confidence_guardrails(0.80, False, 0)
        assert status == CompletenessStatus.Unclear

    def test_mid_range_is_unclear(self):
        """confidence = 0.65 → Unclear."""
        status, _ = apply_confidence_guardrails(0.65, False, 0)
        assert status == CompletenessStatus.Unclear

    def test_exactly_at_unclear_lower_boundary_is_unclear(self):
        """confidence = exactly 0.50 → Unclear (boundary is ≥ 0.50)."""
        status, _ = apply_confidence_guardrails(0.50, False, 0)
        assert status == CompletenessStatus.Unclear

    # ── Absent ────────────────────────────────────────────────────────────────

    def test_low_confidence_is_absent(self):
        """confidence < 0.50 → Absent."""
        status, _ = apply_confidence_guardrails(0.30, False, 0)
        assert status == CompletenessStatus.Absent

    def test_just_below_unclear_boundary_is_absent(self):
        """confidence = 0.499 → Absent (just below the Unclear floor)."""
        status, _ = apply_confidence_guardrails(0.499, False, 0)
        assert status == CompletenessStatus.Absent

    def test_zero_confidence_is_absent(self):
        """confidence = 0.0 → Absent (when parse_failed=False)."""
        status, _ = apply_confidence_guardrails(0.0, False, 0)
        assert status == CompletenessStatus.Absent

    # ── Clamping ──────────────────────────────────────────────────────────────

    def test_confidence_above_1_clamped_to_present(self):
        """confidence > 1.0 should be clamped to 1.0 → Present."""
        status, _ = apply_confidence_guardrails(1.5, False, 0)
        assert status == CompletenessStatus.Present

    def test_confidence_below_0_clamped_to_absent(self):
        """confidence < 0.0 should be clamped to 0.0 → Absent."""
        status, _ = apply_confidence_guardrails(-0.5, False, 0)
        assert status == CompletenessStatus.Absent


# ---------------------------------------------------------------------------
# Guardrail: LLM parse failure → forced Unclear (T020 rule 0)
# ---------------------------------------------------------------------------


class TestParseFailureGuardrail:
    """
    Per spec T020 Guardrail 0 and _parse_llm_response docstring:
      "parse_failed=True → force Unclear, NOT Absent."

    Rationale: a technical failure to parse the LLM's output is not evidence
    of absence. Treating it as Absent would expose a clinical safety risk.
    """

    def test_parse_failure_forces_unclear_not_absent(self):
        status, kw_miss = apply_confidence_guardrails(
            confidence=0.0,  # would normally be Absent
            is_identifier_based=False,
            keyword_miss_count=0,
            parse_failed=True,
        )
        assert status == CompletenessStatus.Unclear
        assert kw_miss is False

    def test_parse_failure_overrides_high_confidence(self):
        """
        Even if the confidence value is 0.99, parse_failed=True still forces Unclear.
        The function should apply Guardrail 0 before any numeric threshold check.
        """
        status, _ = apply_confidence_guardrails(
            confidence=0.99,
            is_identifier_based=False,
            keyword_miss_count=0,
            parse_failed=True,
        )
        assert status == CompletenessStatus.Unclear

    def test_parse_failure_overrides_identifier_based(self):
        """parse_failed takes precedence over the identifier-based keyword miss rule."""
        status, kw_miss = apply_confidence_guardrails(
            confidence=0.90,
            is_identifier_based=True,
            keyword_miss_count=2,
            parse_failed=True,
        )
        assert status == CompletenessStatus.Unclear
        assert kw_miss is False  # the keyword_miss forced flag is NOT set when parse_failed


# ---------------------------------------------------------------------------
# Guardrail: identifier-based + keyword_miss → forced Unclear
# ---------------------------------------------------------------------------


class TestIdentifierBasedKeywordMissGuardrail:
    """
    Per agent-spec.md §Policy Reasoning & Gap Analysis Agent:
    If the requirement is identifier-based (member ID, CPT, HCPCS, ICD-10)
    AND the retrieval agent recorded a keyword miss, the status MUST be Unclear
    regardless of the dense confidence score.
    """

    def test_identifier_based_with_keyword_miss_forces_unclear(self):
        """High confidence does not override the keyword miss for identifier requirements."""
        status, kw_miss_forced = apply_confidence_guardrails(
            confidence=0.95,  # would normally be Present
            is_identifier_based=True,
            keyword_miss_count=1,
        )
        assert status == CompletenessStatus.Unclear
        assert kw_miss_forced is True

    def test_identifier_based_with_multiple_keyword_misses(self):
        status, kw_miss_forced = apply_confidence_guardrails(
            confidence=0.85,
            is_identifier_based=True,
            keyword_miss_count=3,
        )
        assert status == CompletenessStatus.Unclear
        assert kw_miss_forced is True

    def test_identifier_based_without_keyword_miss_uses_normal_thresholds(self):
        """No keyword miss → normal threshold logic applies for identifier requirements."""
        status, kw_miss_forced = apply_confidence_guardrails(
            confidence=0.95,
            is_identifier_based=True,
            keyword_miss_count=0,
        )
        assert status == CompletenessStatus.Present
        assert kw_miss_forced is False

    def test_non_identifier_with_keyword_misses_uses_normal_thresholds(self):
        """Keyword misses are only special-cased for identifier-based requirements."""
        status, kw_miss_forced = apply_confidence_guardrails(
            confidence=0.90,
            is_identifier_based=False,
            keyword_miss_count=5,  # many keyword misses
        )
        assert status == CompletenessStatus.Present
        assert kw_miss_forced is False


# ---------------------------------------------------------------------------
# _parse_llm_response — JSON parsing
# ---------------------------------------------------------------------------


class TestParseLlmResponse:
    """Tests for the internal LLM response parser."""

    def test_valid_json_parsed_correctly(self):
        raw = json.dumps({"confidence": 0.87, "verdict": "Present", "reasoning": "ok"})
        confidence, verdict, failed = _parse_llm_response(raw, "req-001")
        assert confidence == pytest.approx(0.87)
        assert verdict == "Present"
        assert failed is False

    def test_valid_json_absent(self):
        raw = json.dumps({"confidence": 0.30, "verdict": "Absent"})
        confidence, verdict, failed = _parse_llm_response(raw, "req-002")
        assert verdict == "Absent"
        assert failed is False

    def test_markdown_fenced_json_stripped(self):
        raw = "```json\n{\"confidence\": 0.55, \"verdict\": \"Unclear\"}\n```"
        confidence, verdict, failed = _parse_llm_response(raw, "req-003")
        assert verdict == "Unclear"
        assert failed is False

    def test_invalid_json_returns_parse_failed(self):
        raw = "This is not JSON"
        confidence, verdict, failed = _parse_llm_response(raw, "req-004")
        assert failed is True
        assert verdict == "Unclear"

    def test_empty_string_returns_parse_failed(self):
        confidence, verdict, failed = _parse_llm_response("", "req-005")
        assert failed is True

    def test_missing_confidence_key_defaults_to_zero(self):
        """Missing 'confidence' key returns 0.0 (parse_failed=False — JSON valid)."""
        raw = json.dumps({"verdict": "Present"})
        confidence, verdict, failed = _parse_llm_response(raw, "req-006")
        assert confidence == pytest.approx(0.0)
        assert failed is False

    def test_missing_verdict_key_defaults_to_unclear(self):
        raw = json.dumps({"confidence": 0.88})
        confidence, verdict, failed = _parse_llm_response(raw, "req-007")
        assert verdict == "Unclear"

    def test_non_numeric_confidence_returns_parse_failed(self):
        raw = json.dumps({"confidence": "high", "verdict": "Present"})
        _, _, failed = _parse_llm_response(raw, "req-008")
        assert failed is True

    def test_null_response_returns_parse_failed(self):
        _, _, failed = _parse_llm_response("null", "req-009")
        # json.loads("null") returns None — accessing .get() raises AttributeError
        assert failed is True


# ---------------------------------------------------------------------------
# Full guardrail flow: parse → classify
# ---------------------------------------------------------------------------


class TestFullGuardrailPipeline:
    """
    End-to-end: simulate what PolicyReasoningAgent does for each requirement.
    Parse the LLM response then classify via apply_confidence_guardrails.
    """

    def test_valid_high_confidence_present(self):
        raw = json.dumps({"confidence": 0.92, "verdict": "Present"})
        conf, verdict, failed = _parse_llm_response(raw, "r1")
        status, _ = apply_confidence_guardrails(conf, False, 0, failed)
        assert status == CompletenessStatus.Present

    def test_invalid_json_yields_unclear_not_absent(self):
        """
        The most critical safety test: a garbled LLM response must NEVER
        classify a requirement as Absent (which could deny care).
        """
        raw = "ERROR: context window exceeded"
        conf, verdict, failed = _parse_llm_response(raw, "r2")
        status, _ = apply_confidence_guardrails(conf, False, 0, failed)
        assert status == CompletenessStatus.Unclear
        assert status != CompletenessStatus.Absent

    def test_mid_confidence_unclear(self):
        raw = json.dumps({"confidence": 0.65, "verdict": "Unclear"})
        conf, verdict, failed = _parse_llm_response(raw, "r3")
        status, _ = apply_confidence_guardrails(conf, False, 0, failed)
        assert status == CompletenessStatus.Unclear

    def test_low_confidence_absent(self):
        raw = json.dumps({"confidence": 0.25, "verdict": "Absent"})
        conf, verdict, failed = _parse_llm_response(raw, "r4")
        status, _ = apply_confidence_guardrails(conf, False, 0, failed)
        assert status == CompletenessStatus.Absent
