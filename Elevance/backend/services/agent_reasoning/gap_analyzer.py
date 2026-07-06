from typing import List, Dict, Any
from .conflict_detector import detect_conflicts
import uuid

def analyze_gap(criterion: str, evidence_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Evaluates evidence against a criterion, applies confidence thresholds, and handles conflicts.
    """
    # 1. Detect conflicts
    if detect_conflicts(evidence_items):
        return {
            "criterion": criterion,
            "status": "unclear",
            "rationale": "Contradictory evidence detected regarding this criterion.",
            "evidence_refs": [e.get("evidence_id") for e in evidence_items if e.get("evidence_id")],
            "conflict_detected": True,
            "confidence_level": "escalate" # Conflicts route to escalate logic, handled by Workflow agent
        }
        
    # 2. Base evaluation
    if not evidence_items:
        return {
            "criterion": criterion,
            "status": "absent",
            "rationale": "No evidence found to support this criterion.",
            "evidence_refs": [],
            "conflict_detected": False,
            "confidence_level": "normal"
        }
        
    # 3. Calculate aggregate confidence (mock: average of evidence confidence)
    confidences = [e.get("confidence", 0.0) for e in evidence_items]
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    
    # Apply confidence thresholds
    # < 0.6: auto-escalate
    # 0.6 - 0.8: surface with caution
    # > 0.8: present normally
    confidence_level = "normal"
    if avg_confidence < 0.6:
        confidence_level = "escalate"
    elif avg_confidence <= 0.8:
        confidence_level = "caution"
        
    evidence_refs = [e.get("evidence_id") for e in evidence_items if e.get("evidence_id")]
    
    # Ensure evidence_refs is non-empty if status is present
    status = "present"
    if not evidence_refs:
        status = "unclear"
        
    return {
        "criterion": criterion,
        "status": status,
        "rationale": "Evidence supports this criterion.",
        "evidence_refs": evidence_refs,
        "conflict_detected": False,
        "confidence_level": confidence_level
    }
