from fastapi import FastAPI
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Literal
import uuid

from .gap_analyzer import analyze_gap

app = FastAPI(title="Policy Reasoning & Gap Agent")

class EvidenceItem(BaseModel):
    evidence_id: str
    matched_text: str
    confidence: float
    source_name: str

class GapAnalysisRequest(BaseModel):
    case_id: str
    criteria: List[str]
    evidence: List[EvidenceItem]

class GapChecklistItem(BaseModel):
    model_config = ConfigDict(extra='forbid')
    
    criterion: str
    status: Literal["present", "absent", "unclear"]
    rationale: str
    evidence_refs: List[str]
    conflict_detected: bool
    confidence_level: str

class GapAnalysisResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')
    
    case_id: str
    checklist: List[GapChecklistItem]
    # No approval/denial or overall status allowed

@app.post("/analyze", response_model=GapAnalysisResponse)
async def analyze_case_gaps(request: GapAnalysisRequest):
    checklist = []
    
    for criterion in request.criteria:
        # Filter evidence for this criterion (mock logic: all evidence applies)
        relevant_evidence = [e.dict() for e in request.evidence]
        
        result = analyze_gap(criterion, relevant_evidence)
        checklist.append(GapChecklistItem(**result))
        
    return GapAnalysisResponse(
        case_id=request.case_id,
        checklist=checklist
    )
