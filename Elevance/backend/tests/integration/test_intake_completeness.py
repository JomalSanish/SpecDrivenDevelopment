import pytest
from shared.models.case import Case, RequestType
from shared.models.document import Document, DocumentType
from services.agent_intake.classifier import determine_completeness

def test_completeness_missing_clinical_note():
    # A case with no documents
    case = Case(
        member_id="M123",
        provider_id="P456",
        request_type=RequestType.IMAGING
    )
    
    result = determine_completeness(case.documents, case.request_type)
    assert result["is_complete"] is False
    assert "clinical_note" in result["missing_fields"]

def test_completeness_with_clinical_note():
    case = Case(
        member_id="M123",
        provider_id="P456",
        request_type=RequestType.IMAGING
    )
    doc = Document(type=DocumentType.CLINICAL_NOTE, source="upload")
    case.documents.append(doc)
    
    result = determine_completeness(case.documents, case.request_type)
    assert result["is_complete"] is True
    assert len(result["missing_fields"]) == 0

def test_specialty_referral_requires_referral_form():
    case = Case(
        member_id="M123",
        provider_id="P456",
        request_type=RequestType.SPECIALTY_REFERRAL
    )
    doc = Document(type=DocumentType.CLINICAL_NOTE, source="upload")
    case.documents.append(doc)
    
    result = determine_completeness(case.documents, case.request_type)
    assert result["is_complete"] is False
    assert "referral_form" in result["missing_fields"]
    
    doc2 = Document(type=DocumentType.REFERRAL_FORM, source="upload")
    case.documents.append(doc2)
    
    result2 = determine_completeness(case.documents, case.request_type)
    assert result2["is_complete"] is True
