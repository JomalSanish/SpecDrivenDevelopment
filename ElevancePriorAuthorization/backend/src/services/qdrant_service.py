"""
backend/src/services/qdrant_service.py

Qdrant vector-store service for the PA Evidence Assistant.

Responsibilities:
  1. Manage the single Qdrant collection (`pa-evidence`) with dense + sparse
     (BM25) vector configurations.
  2. Index document chunks: each point carries a `case_id` payload so every
     query is strictly partitioned by case (rag-pipeline.md §Indexing & Isolation).
  3. Retrieve Top-K candidates for a given query using:
       - Dense semantic similarity (BAAI/bge-large-en-v1.5, 1024-dim)
       - Sparse BM25 keyword search (native Qdrant sparse vectors)
     Both are returned separately for downstream RRF fusion (T017).

Constitution §II: ALL inference (embeddings) uses the local TEI endpoint
sourced through the secrets abstraction — never a public API.

Constitution §V: Qdrant host/port are fetched via get_secret(), not raw env.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    SparseIndexParams,
    SparseVectorParams,
    VectorParams,
    ScoredPoint,
    SearchRequest,
    NamedVector,
    NamedSparseVector,
    SparseVector,
    HnswConfigDiff,
)

from src.core.secrets import get_secret

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

COLLECTION_NAME = "pa-evidence"
DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"
DENSE_DIM = 1024  # BAAI/bge-large-en-v1.5 output dimension

# Payload field names
PAYLOAD_CASE_ID = "case_id"
PAYLOAD_DOCUMENT_ID = "document_id"
PAYLOAD_CHUNK_ID = "chunk_id"
PAYLOAD_PAGE_NUMBER = "page_number"
PAYLOAD_TEXT = "text"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ChunkPayload:
    """
    Metadata that accompanies each indexed vector point.
    rag-pipeline.md: Each chunk MUST carry case_id, document_id,
    page_number, and chunk_id (UUID).
    """

    case_id: str
    document_id: str
    chunk_id: str
    page_number: int
    text: str
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class IndexedChunk:
    """Input to the indexer: pre-computed vectors + payload."""

    payload: ChunkPayload
    dense_vector: list[float]
    sparse_indices: list[int]
    sparse_values: list[float]


@dataclass
class RetrievedChunk:
    """One result from a dense or sparse search."""

    chunk_id: str
    case_id: str
    document_id: str
    page_number: int
    text: str
    score: float
    source: str  # "dense" | "sparse"


# ---------------------------------------------------------------------------
# Embedding client (wraps local TEI endpoint)
# ---------------------------------------------------------------------------


class LocalEmbeddingClient:
    """
    Calls the locally deployed TEI / SentenceTransformers embedding endpoint.
    Constitution §II: endpoint sourced from secrets — never a public API.

    TEI exposes an OpenAI-compatible endpoint:
      POST /embed   → list[list[float]]
    """

    def __init__(self) -> None:
        self._endpoint = (
            get_secret("EMBEDDING_ENDPOINT") or "http://localhost:8080"
        ).rstrip("/")
        self._embed_url = f"{self._endpoint}/embed"
        logger.info("LocalEmbeddingClient: endpoint=%s", self._endpoint)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Embed a batch of texts using the local TEI service.
        Returns a list of dense float vectors (one per input text).

        Raises RuntimeError if the embedding service is unreachable.
        """
        if not texts:
            return []

        payload = {"inputs": texts, "normalize": True, "truncate": True}

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(self._embed_url, json=payload)
                response.raise_for_status()
            except httpx.ConnectError as exc:
                raise RuntimeError(
                    f"Embedding service unreachable at {self._embed_url}. "
                    "Is the TEI container running? (docker-compose up -d tei)"
                ) from exc
            except httpx.HTTPStatusError as exc:
                raise RuntimeError(
                    f"Embedding request failed: {exc.response.status_code} "
                    f"{exc.response.text[:300]}"
                ) from exc

        vectors = response.json()
        if not isinstance(vectors, list) or not vectors:
            raise RuntimeError(
                f"Embedding service returned unexpected format: {type(vectors)}"
            )
        return vectors

    async def embed_one(self, text: str) -> list[float]:
        """Embed a single text string."""
        return (await self.embed([text]))[0]

    async def health_check(self) -> dict[str, Any]:
        """
        Check if the embedding service is reachable.
        Returns {"status": "ok", "endpoint": ...} on success.
        Raises RuntimeError on failure.
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.get(f"{self._endpoint}/health")
                response.raise_for_status()
                return {"status": "ok", "endpoint": self._endpoint, "detail": response.json()}
            except (httpx.ConnectError, httpx.HTTPStatusError) as exc:
                raise RuntimeError(
                    f"Embedding service health check failed at {self._endpoint}: {exc}"
                ) from exc


# ---------------------------------------------------------------------------
# BM25 sparse tokeniser (local — no network calls)
# ---------------------------------------------------------------------------


def _bm25_tokenise(text: str) -> tuple[list[int], list[float]]:
    """
    Convert *text* to a sparse bag-of-words representation compatible with
    Qdrant's sparse vector format.

    Uses a stable hash-based vocabulary: token → int index. IMPORTANT: this
    must use a hash function that is stable ACROSS process restarts, not
    Python's built-in hash(), which is randomised per-process (PYTHONHASHSEED)
    for str objects since Python 3.3. Using hash() here would silently
    invalidate every previously-indexed sparse vector on every container
    restart, with no error — the sparse/BM25 half of hybrid retrieval would
    quietly stop matching anything indexed before the restart.

    BM25 term frequencies are approximated by raw term frequency (TF); full
    IDF weighting is delegated to Qdrant's built-in sparse index. (Note: this
    is TF only, not a full BM25 formula — Qdrant's sparse index does not
    apply BM25-specific document-length normalisation on its own.)

    Returns:
        indices — sorted list of unique token hash indices
        values  — corresponding TF weights (float32)
    """
    import re
    import math
    import hashlib

    def _stable_hash(token: str) -> int:
        """Process-independent hash — same token always maps to the same
        index, regardless of PYTHONHASHSEED or process restarts."""
        digest = hashlib.md5(token.encode("utf-8")).hexdigest()
        return int(digest, 16) % (2**20)  # 1M-bucket vocabulary

    tokens = re.findall(r"\b[a-zA-Z0-9]+\b", text.lower())
    tf: dict[int, int] = {}
    for token in tokens:
        idx = _stable_hash(token)
        tf[idx] = tf.get(idx, 0) + 1

    total = sum(tf.values()) or 1
    sorted_items = sorted(tf.items())
    indices = [i for i, _ in sorted_items]
    # Log-normalised TF so very long chunks don't dominate
    values = [math.log1p(c / total) for _, c in sorted_items]
    return indices, values


# ---------------------------------------------------------------------------
# QdrantIndexingService
# ---------------------------------------------------------------------------


class QdrantIndexingService:
    """
    Manages the Qdrant collection lifecycle and provides index / search
    operations for the PA Evidence RAG pipeline.

    Qdrant connection details are sourced from the secrets abstraction
    (Constitution §V — never raw env access).
    """

    def __init__(self) -> None:
        host = get_secret("QDRANT_HOST") or "localhost"
        port_str = get_secret("QDRANT_PORT") or "6333"
        self._client = AsyncQdrantClient(host=host, port=int(port_str))
        self._embedding_client = LocalEmbeddingClient()
        logger.info(
            "QdrantIndexingService: host=%s port=%s collection=%s",
            host,
            port_str,
            COLLECTION_NAME,
        )

    # ------------------------------------------------------------------
    # Collection management
    # ------------------------------------------------------------------

    async def ensure_collection(self) -> None:
        """
        Create the Qdrant collection if it does not already exist.

        Vector config:
          - dense  : 1024-dim float, Cosine distance (BAAI/bge-large-en-v1.5)
          - sparse : BM25 token indices, inner-product similarity
        """
        existing = await self._client.get_collections()
        names = {c.name for c in existing.collections}

        if COLLECTION_NAME not in names:
            await self._client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config={
                    DENSE_VECTOR_NAME: VectorParams(
                        size=DENSE_DIM,
                        distance=Distance.COSINE,
                        hnsw_config=HnswConfigDiff(m=16, ef_construct=100),
                    ),
                },
                sparse_vectors_config={
                    SPARSE_VECTOR_NAME: SparseVectorParams(
                        index=SparseIndexParams(full_scan_threshold=5000),
                    ),
                },
            )
            logger.info("Created Qdrant collection '%s'.", COLLECTION_NAME)
        else:
            logger.debug("Qdrant collection '%s' already exists.", COLLECTION_NAME)

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    async def index_chunks(self, chunks: list[IndexedChunk]) -> int:
        """
        Upsert *chunks* into Qdrant.

        Each point carries a `case_id` payload so queries can be strictly
        partitioned (rag-pipeline.md §Indexing & Isolation).

        Returns number of points successfully upserted.
        """
        if not chunks:
            return 0

        points = []
        for chunk in chunks:
            p = chunk.payload
            point_id = str(uuid.UUID(p.chunk_id))  # normalise to UUID string
            payload: dict[str, Any] = {
                PAYLOAD_CASE_ID: p.case_id,
                PAYLOAD_DOCUMENT_ID: p.document_id,
                PAYLOAD_CHUNK_ID: p.chunk_id,
                PAYLOAD_PAGE_NUMBER: p.page_number,
                PAYLOAD_TEXT: p.text,
                **p.extra,
            }
            points.append(
                PointStruct(
                    id=point_id,
                    vector={
                        DENSE_VECTOR_NAME: chunk.dense_vector,
                        SPARSE_VECTOR_NAME: SparseVector(
                            indices=chunk.sparse_indices,
                            values=chunk.sparse_values,
                        ),
                    },
                    payload=payload,
                )
            )

        await self._client.upsert(
            collection_name=COLLECTION_NAME,
            points=points,
            wait=True,
        )
        logger.info(
            "Indexed %d chunks into Qdrant collection '%s'.",
            len(points),
            COLLECTION_NAME,
        )
        return len(points)

    async def index_text_chunks(
        self,
        case_id: str,
        document_id: str,
        texts: list[str],
        page_numbers: Optional[list[int]] = None,
    ) -> int:
        """
        Convenience method: embed *texts* locally and index into Qdrant.

        *page_numbers* defaults to sequential integers if not provided.
        Returns number of points upserted.
        """
        if not texts:
            return 0

        page_numbers = page_numbers or list(range(len(texts)))
        dense_vectors = await self._embedding_client.embed(texts)

        chunks: list[IndexedChunk] = []
        for i, (text, dense_vec, page_num) in enumerate(
            zip(texts, dense_vectors, page_numbers)
        ):
            sparse_indices, sparse_values = _bm25_tokenise(text)
            chunk_id = str(uuid.uuid4())
            chunks.append(
                IndexedChunk(
                    payload=ChunkPayload(
                        case_id=case_id,
                        document_id=document_id,
                        chunk_id=chunk_id,
                        page_number=page_num,
                        text=text,
                    ),
                    dense_vector=dense_vec,
                    sparse_indices=sparse_indices,
                    sparse_values=sparse_values,
                )
            )

        return await self.index_chunks(chunks)

    # ------------------------------------------------------------------
    # Retrieval (dense and sparse searched separately for RRF in T017)
    # ------------------------------------------------------------------

    def _case_filter(self, case_id: str) -> Filter:
        """
        Strict case_id payload filter.

        Constitution §III / rag-pipeline.md: Every query MUST be scoped to
        a single case_id to prevent cross-case data leakage.
        """
        return Filter(
            must=[
                FieldCondition(
                    key=PAYLOAD_CASE_ID,
                    match=MatchValue(value=case_id),
                )
            ]
        )

    async def search_dense(
        self,
        query_text: str,
        case_id: str,
        top_k: int = 10,
    ) -> list[RetrievedChunk]:
        """
        Semantic dense search scoped strictly to *case_id*.

        Embeds *query_text* locally and queries the dense HNSW index.
        """
        query_vec = await self._embedding_client.embed_one(query_text)
        results: list[ScoredPoint] = await self._client.search(
            collection_name=COLLECTION_NAME,
            query_vector=NamedVector(name=DENSE_VECTOR_NAME, vector=query_vec),
            query_filter=self._case_filter(case_id),
            limit=top_k,
            with_payload=True,
        )
        return [self._to_retrieved(pt, source="dense") for pt in results]

    async def search_sparse(
        self,
        query_text: str,
        case_id: str,
        top_k: int = 10,
    ) -> list[RetrievedChunk]:
        """
        BM25 sparse keyword search scoped strictly to *case_id*.

        Tokenises *query_text* locally (no network call) and queries the
        sparse index.  This is the primary path for exact-match identifier
        fields (member ID, CPT/HCPCS, ICD-10) per rag-pipeline.md
        §Exact-Match Identifier Coverage.
        """
        sparse_indices, sparse_values = _bm25_tokenise(query_text)
        results: list[ScoredPoint] = await self._client.search(
            collection_name=COLLECTION_NAME,
            query_vector=NamedSparseVector(
                name=SPARSE_VECTOR_NAME,
                vector=SparseVector(
                    indices=sparse_indices,
                    values=sparse_values,
                ),
            ),
            query_filter=self._case_filter(case_id),
            limit=top_k,
            with_payload=True,
        )
        return [self._to_retrieved(pt, source="sparse") for pt in results]

    @staticmethod
    def _to_retrieved(point: ScoredPoint, source: str) -> RetrievedChunk:
        p = point.payload or {}
        return RetrievedChunk(
            chunk_id=str(p.get(PAYLOAD_CHUNK_ID, point.id)),
            case_id=str(p.get(PAYLOAD_CASE_ID, "")),
            document_id=str(p.get(PAYLOAD_DOCUMENT_ID, "")),
            page_number=int(p.get(PAYLOAD_PAGE_NUMBER, 0)),
            text=str(p.get(PAYLOAD_TEXT, "")),
            score=float(point.score),
            source=source,
        )

    # ------------------------------------------------------------------
    # Delete helpers
    # ------------------------------------------------------------------

    async def delete_case_chunks(self, case_id: str) -> None:
        """Remove all indexed points for *case_id* (e.g. on case deletion)."""
        await self._client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key=PAYLOAD_CASE_ID,
                        match=MatchValue(value=case_id),
                    )
                ]
            ),
            wait=True,
        )
        logger.info("Deleted all Qdrant chunks for case_id=%s.", case_id)

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    async def health_check(self) -> dict[str, Any]:
        """Return Qdrant + embedding service health info."""
        qdrant_ok = await self._client.get_collections()
        embedding_status = await self._embedding_client.health_check()
        return {
            "qdrant": {
                "status": "ok",
                "collections": [c.name for c in qdrant_ok.collections],
            },
            "embedding": embedding_status,
        }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_service_instance: Optional[QdrantIndexingService] = None


def get_qdrant_service() -> QdrantIndexingService:
    """Return the process-level QdrantIndexingService singleton (lazy init)."""
    global _service_instance
    if _service_instance is None:
        _service_instance = QdrantIndexingService()
    return _service_instance
