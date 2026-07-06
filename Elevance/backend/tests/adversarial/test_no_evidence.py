import pytest
from services.agent_rag.search import hybrid_search

def test_no_evidence_returns_insufficient():
    """
    Constitution Check: GROUNDED, CITED OUTPUTS ONLY
    Verifies that querying for something not in the knowledge base returns an empty array,
    triggering the Insufficient Evidence fallback in the RAG endpoint.
    """
    # Using the mocked hybrid_search which returns empty for "missing"
    results = hybrid_search("missing document test")
    assert len(results) == 0
    # The router logic handles the mapping to "Insufficient Evidence", 
    # which is verified in the integration test scope.
