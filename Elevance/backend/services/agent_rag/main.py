from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Any
import uuid

# Import our RAG components
from .chunking import chunk_text
from .embeddings import generate_embeddings
from .search import hybrid_search
from .citation import extract_citations

app = FastAPI(title="Evidence Retrieval RAG Agent")

class SearchQuery(BaseModel):
    query: str
    case_id: str

class EvidenceResponse(BaseModel):
    evidence_items: List[Any]
    message: str = "Success"

@app.post("/retrieve", response_model=EvidenceResponse)
async def retrieve_evidence(request: SearchQuery):
    # 1. (Simulated) Chunking and Embedding of the case documents would have happened at ingestion
    
    # 2. Perform Hybrid Search
    results = hybrid_search(request.query)
    
    # 3. Add citations
    cited_results = extract_citations(results)
    
    # 4. Fallback for Insufficient Evidence
    if not cited_results:
        return EvidenceResponse(
            evidence_items=[{
                "criterion": request.query,
                "status": "unclear",
                "matched_text": "Insufficient Evidence",
                "source_name": "N/A",
                "confidence": 0.0
            }],
            message="Insufficient Evidence"
        )
        
    # Standard response mapping
    mapped = []
    for r in cited_results:
        mapped.append({
            "criterion": request.query,
            "status": "present",  # RAG just finds text, Reasoning agent evaluates. But to match contract:
            "matched_text": r.get("matched_text"),
            "source_name": r.get("citation", r.get("source_name")),
            "confidence": r.get("confidence")
        })
        
    return EvidenceResponse(evidence_items=mapped)
