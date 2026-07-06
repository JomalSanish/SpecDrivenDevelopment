import pytest
from services.agent_reasoning.gap_analyzer import analyze_gap

def test_low_confidence_auto_escalates():
    """
    Verifies that if aggregate confidence is < 0.6, it auto-flags for manual review.
    """
    mock_evidence = [
        {"evidence_id": "1", "matched_text": "Vague mention of condition", "confidence": 0.55}
    ]
    
    result = analyze_gap("Patient must have condition X", mock_evidence)
    
    assert result["confidence_level"] == "escalate"
    assert result["conflict_detected"] is False
    assert result["status"] == "present" # It found evidence, but confidence is low
