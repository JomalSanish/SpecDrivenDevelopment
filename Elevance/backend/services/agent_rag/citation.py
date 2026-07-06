from typing import List, Dict, Any

def format_citation(source_name: str, chunk_index: int, total_chunks: int) -> str:
    """
    Formats the citation string for a given text chunk.
    """
    return f"[{source_name} (Section {chunk_index+1}/{total_chunks})]"

def extract_citations(evidence_chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Enriches evidence chunks with formatted citations.
    """
    for chunk in evidence_chunks:
        chunk["citation"] = format_citation(
            chunk.get("source_name", "Unknown Source"),
            chunk.get("chunk_index", 0),
            chunk.get("total_chunks", 1)
        )
    return evidence_chunks
