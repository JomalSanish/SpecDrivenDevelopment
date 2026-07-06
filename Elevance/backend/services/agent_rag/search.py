from typing import List, Dict, Any

def hybrid_search(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """
    Performs hybrid search (Semantic + Keyword via RRF).
    Mocked for MVP.
    """
    if "missing policy" in query.lower():
        return []
        
    if "contradict" in query.lower():
        return [
            {"matched_text": "Patient has condition X.", "confidence": 0.9, "source_name": "clinical_note.pdf"},
            {"matched_text": "Patient does NOT have condition X.", "confidence": 0.88, "source_name": "referral.pdf"}
        ]
        
    if "missing" in query.lower() or "unclear" in query.lower():
        return []
        
    return [
        {"matched_text": f"Mocked evidence for {query}", "confidence": 0.95, "source_name": "clinical_note.pdf"}
    ]
