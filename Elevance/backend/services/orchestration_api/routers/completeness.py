from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from shared.db import get_db
from shared.models.case import Case
from services.agent_intake.classifier import determine_completeness
from pydantic import BaseModel
from typing import List

router = APIRouter()

class CompletenessResponse(BaseModel):
    is_complete: bool
    missing_fields: List[str]

@router.get("/{case_id}/completeness", response_model=CompletenessResponse)
def check_completeness(case_id: str, db: Session = Depends(get_db)):
    case = db.query(Case).filter(Case.case_id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
        
    result = determine_completeness(case.documents, case.request_type)
    return CompletenessResponse(
        is_complete=result["is_complete"],
        missing_fields=result["missing_fields"]
    )
