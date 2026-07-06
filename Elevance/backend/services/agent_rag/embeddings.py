from typing import List

def generate_embeddings(texts: List[str]) -> List[List[float]]:
    """
    Generates embeddings for a list of text chunks.
    For the MVP, this mocks the API call to Anthropic/OpenAI or uses a local model.
    """
    # Mocking a 1536-dimensional vector for MVP compatibility
    return [[0.0] * 1536 for _ in texts]
