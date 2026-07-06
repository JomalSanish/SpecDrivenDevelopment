import pytest
from pydantic import ValidationError
from services.agent_reasoning.main import GapAnalysisResponse, GapChecklistItem

def test_no_approval_fields_allowed_in_schema():
    """
    Constitution Check: HUMAN-IN-THE-LOOP ONLY
    Verifies that the agent output schema absolutely cannot contain
    fields like 'approved', 'denied', or 'decision'.
    """
    # Valid schema works
    valid_item = GapChecklistItem(
        criterion="Test",
        status="present",
        rationale="Evidence exists",
        evidence_refs=["uuid-1"],
        conflict_detected=False,
        confidence_level="normal"
    )
    assert valid_item.status == "present"
    
    # Invalid schema (attempting to output approval) fails Pydantic validation
    with pytest.raises(ValidationError) as exc_info:
        invalid_item = GapChecklistItem(
            criterion="Test",
            status="present",
            rationale="Evidence exists",
            evidence_refs=["uuid-1"],
            conflict_detected=False,
            confidence_level="normal",
            approved=True  # This MUST fail
        )
        
    assert "Extra inputs are not permitted" in str(exc_info.value)
    
    with pytest.raises(ValidationError) as exc_info:
        GapChecklistItem(
            criterion="Test",
            status="approved", # Must be present, absent, unclear
            rationale="Approved because of evidence",
            evidence_refs=["uuid-1"],
            conflict_detected=False,
            confidence_level="normal"
        )
    # Status enum restriction might not be explicitly enum mapped in basic Pydantic,
    # but the test proves we can't add `decision` fields.
    
    with pytest.raises(ValidationError) as exc_info:
        invalid_item_2 = GapChecklistItem(
            criterion="Test",
            status="present",
            rationale="Evidence exists",
            evidence_refs=["uuid-1"],
            conflict_detected=False,
            confidence_level="normal",
            decision="approve"  # This MUST fail
        )
        
    assert "Extra inputs are not permitted" in str(exc_info.value)

def test_response_wrapper_no_approval():
    with pytest.raises(ValidationError) as exc_info:
        GapAnalysisResponse(
            case_id="123",
            checklist=[],
            case_status="approved" # MUST fail
        )
    assert "Extra inputs are not permitted" in str(exc_info.value)
