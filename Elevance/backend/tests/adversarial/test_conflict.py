import pytest
from services.agent_reasoning.gap_analyzer import analyze_gap

def test_contradictory_evidence_flags_conflict():
    """
    Verifies that conflicting evidence (e.g., patient has X, patient does not have X)
    triggers conflict_detected=True and status=unclear.
    """
    mock_evidence = [
        {"evidence_id": "1", "matched_text": "Patient has condition X", "confidence": 0.9},
        {"evidence_id": "2", "matched_text": "Patient does NOT have condition X", "confidence": 0.9}
    ]
    
    result = analyze_gap("Patient must have condition X", mock_evidence)
    
    assert result["conflict_detected"] is True
    assert result["status"] == "unclear"
    assert result["confidence_level"] == "escalate"
