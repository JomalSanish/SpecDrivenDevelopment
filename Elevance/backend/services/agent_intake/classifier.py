from typing import Dict, Any, List
from sqlalchemy.orm import Session
from shared.models.case import Case, CaseStatus
from shared.models.document import Document, DocumentType
from shared.db import SessionLocal

def detect_duplicates(db: Session, member_id: str, request_type: str, cpt_codes: List[str]) -> bool:
    """
    [FR-002] Implement duplicate case detection logic.
    Checks if a recent case exists for the same member, request type, and overlapping CPT codes.
    """
    # Simple logic for duplicate detection:
    # A real implementation would check time boundaries (e.g. within 30 days)
    existing_cases = db.query(Case).filter(
        Case.member_id == member_id,
        Case.request_type == request_type,
        Case.status != CaseStatus.AWAITING_PROVIDER_DOCUMENTATION # Or other terminal states
    ).all()
    
    for ec in existing_cases:
        if any(code in ec.cpt_hcpcs_codes for code in cpt_codes):
            return True
            
    return False

def determine_completeness(documents: List[Document], request_type: str) -> Dict[str, Any]:
    """
    Determine if the case has the required documents based on request type.
    """
    has_clinical = any(d.type == DocumentType.CLINICAL_NOTE for d in documents)
    has_referral = any(d.type == DocumentType.REFERRAL_FORM for d in documents)
    
    missing = []
    if not has_clinical:
        missing.append("clinical_note")
        
    if request_type == "specialty referral" and not has_referral:
        missing.append("referral_form")
        
    return {
        "is_complete": len(missing) == 0,
        "missing_fields": missing
    }

def classify_case(case_id: str) -> Dict[str, Any]:
    """
    Classify the case and check completeness.
    """
    db = SessionLocal()
    try:
        case = db.query(Case).filter(Case.case_id == case_id).first()
        if not case:
            return {"error": "Case not found"}
            
        is_duplicate = detect_duplicates(db, case.member_id, case.request_type, case.cpt_hcpcs_codes)
        if is_duplicate:
            # We could mark the case as duplicate or return a flag
            pass
            
        completeness = determine_completeness(case.documents, case.request_type)
        
        # Update state based on completeness
        if not completeness["is_complete"]:
            case.status = CaseStatus.INTAKE_REVIEW
        else:
            case.status = CaseStatus.READY_FOR_EVIDENCE_REVIEW
            
        db.commit()
        
        return {
            "case_id": case_id,
            "is_duplicate": is_duplicate,
            "completeness": completeness,
            "new_status": case.status.value
        }
    finally:
        db.close()
