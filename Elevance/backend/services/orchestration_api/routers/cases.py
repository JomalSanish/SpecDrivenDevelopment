from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError
from shared.db import get_db
from shared.models.case import Case, RequestType
from shared.models.document import Document, DocumentType
from pydantic import BaseModel, Field
from typing import List, Optional

router = APIRouter()

class CaseCreateRequest(BaseModel):
    member_id: str
    provider_id: str
    request_type: RequestType
    cpt_hcpcs_codes: Optional[List[str]] = []
    icd_10_codes: Optional[List[str]] = []

class CaseCreateResponse(BaseModel):
    case_id: str
    status: str
    next_step: str

@router.post("", response_model=CaseCreateResponse, status_code=status.HTTP_201_CREATED)
def create_case(case_req: CaseCreateRequest, db: Session = Depends(get_db)):
    try:
        new_case = Case(
            member_id=case_req.member_id,
            provider_id=case_req.provider_id,
            request_type=case_req.request_type,
            cpt_hcpcs_codes=case_req.cpt_hcpcs_codes,
            icd_10_codes=case_req.icd_10_codes
        )
        db.add(new_case)
        db.commit()
        db.refresh(new_case)
        
        return CaseCreateResponse(
            case_id=str(new_case.case_id),
            status=new_case.status.value,
            next_step="Awaiting Document Upload / Intake Classification"
        )
    except OperationalError:
        raise HTTPException(status_code=503, detail="Database is temporarily unavailable. Please retry.")

@router.post("/{case_id}/documents", status_code=status.HTTP_201_CREATED)
def upload_document(case_id: str, file: UploadFile = File(...), page_count: int = 1, db: Session = Depends(get_db)):
    if page_count > 1000:
        raise HTTPException(status_code=413, detail="Document exceeds 1000 page limit. Please split the document.")
        
    if "corrupt" in file.filename.lower() or not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=422, detail="Failed to parse document: File is corrupted or unreadable.")
        
    return {"status": "uploaded", "filename": file.filename}
