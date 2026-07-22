"""
backend/src/services/fusion_service.py

Reciprocal Rank Fusion (RRF) for combining dense + sparse BM25 retrieval
result lists.

Specification (rag-pipeline.md §Hybrid Retrieval & Fusion):
  - Dense Vector : 384-dim float from bge-small-en-v1.5 (HNSW, Cosine)
  - Sparse Vector : BM25 token indices (Qdrant native sparse)
  - Fusion        : RRF with configurable k constant (default k=60 per
                    standard RRF paper: Cormack et al., 2009)

Also enforces the Dense-Hit / Keyword-Miss rule (rag-pipeline.md
§Dense-Hit / Keyword-Miss Handling):
  - When a candidate has a strong dense score but NO corresponding sparse
    (BM25) hit AND the requirement is identifier-based, its effective status
    cap is "Unclear", not "Present".
  - This is signalled via the `keyword_miss` flag on FusedResult.

All processing is in-memory (no network calls — Constitution §II).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from src.services.qdrant_service import RetrievedChunk

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Standard RRF constant — controls smoothing. Higher k favours lower-ranked
# results; k=60 is the standard value from the original paper.
DEFAULT_RRF_K = 60

# Minimum score threshold to include a candidate in fused results
DEFAULT_MIN_SCORE = 0.0


# ---------------------------------------------------------------------------
# Output data class
# ---------------------------------------------------------------------------


@dataclass
class FusedResult:
    """
    A single candidate after RRF fusion, ready for the Reasoning Agent.

    Fields:
      chunk_id     — stable UUID for citation purposes (SEC-004)
      case_id      — owning case (always validated)
      document_id  — source document UUID for citation
      page_number  — source page number
      text         — chunk text
      rrf_score    — combined RRF score (higher = more relevant)
      dense_score  — raw dense similarity score (or None if absent)
      sparse_score — raw BM25 score (or None if absent)
      keyword_miss — True if this candidate has a dense hit but NO sparse/BM25
                     hit. The Reasoning Agent MUST cap such items at "Unclear"
                     for identifier-based requirements (rag-pipeline.md
                     §Dense-Hit / Keyword-Miss Handling).
    """

    chunk_id: str
    case_id: str
    document_id: str
    page_number: int
    text: str
    rrf_score: float
    dense_score: Optional[float] = None
    sparse_score: Optional[float] = None
    keyword_miss: bool = False


# ---------------------------------------------------------------------------
# RRF core
# ---------------------------------------------------------------------------


def reciprocal_rank_fusion(
    dense_results: list[RetrievedChunk],
    sparse_results: list[RetrievedChunk],
    k: int = DEFAULT_RRF_K,
    top_k: int = 10,
    min_score: float = DEFAULT_MIN_SCORE,
) -> list[FusedResult]:
    """
    Combine *dense_results* and *sparse_results* using Reciprocal Rank Fusion.

    RRF score for candidate d:
        RRF(d) = Σ  1 / (k + rank_i(d))
               for each result list i where d appears

    Steps:
    1. Assign 1-based ranks within each result list.
    2. Accumulate RRF score per unique chunk_id.
    3. Flag candidates where ONLY a dense hit exists (keyword_miss=True).
    4. Sort by descending RRF score and return top_k candidates.

    Parameters
    ----------
    dense_results  : Results from QdrantIndexingService.search_dense()
    sparse_results : Results from QdrantIndexingService.search_sparse()
    k              : RRF smoothing constant (default 60)
    top_k          : Maximum number of fused results to return
    min_score      : Drop candidates below this RRF score

    Returns
    -------
    List of FusedResult, sorted by descending rrf_score, max length top_k.
    """
    # ---- Build per-list rank maps ----------------------------------------
    dense_ranks: dict[str, int] = {}
    for rank, chunk in enumerate(dense_results, start=1):
        dense_ranks[chunk.chunk_id] = rank

    sparse_ranks: dict[str, int] = {}
    for rank, chunk in enumerate(sparse_results, start=1):
        sparse_ranks[chunk.chunk_id] = rank

    # ---- Collect chunk metadata from both lists --------------------------
    chunk_meta: dict[str, RetrievedChunk] = {}
    for chunk in dense_results:
        chunk_meta[chunk.chunk_id] = chunk
    for chunk in sparse_results:
        # Prefer dense meta (same chunk, richer content), keep sparse if new
        chunk_meta.setdefault(chunk.chunk_id, chunk)

    # ---- Compute RRF scores ----------------------------------------------
    all_chunk_ids = set(dense_ranks) | set(sparse_ranks)
    fused: list[FusedResult] = []

    for chunk_id in all_chunk_ids:
        rrf_score = 0.0
        if chunk_id in dense_ranks:
            rrf_score += 1.0 / (k + dense_ranks[chunk_id])
        if chunk_id in sparse_ranks:
            rrf_score += 1.0 / (k + sparse_ranks[chunk_id])

        if rrf_score < min_score:
            continue

        meta = chunk_meta[chunk_id]

        # Dense-hit / keyword-miss detection
        keyword_miss = (chunk_id in dense_ranks) and (chunk_id not in sparse_ranks)

        # Retrieve raw scores for transparency
        dense_score = (
            next((c.score for c in dense_results if c.chunk_id == chunk_id), None)
        )
        sparse_score = (
            next((c.score for c in sparse_results if c.chunk_id == chunk_id), None)
        )

        fused.append(
            FusedResult(
                chunk_id=chunk_id,
                case_id=meta.case_id,
                document_id=meta.document_id,
                page_number=meta.page_number,
                text=meta.text,
                rrf_score=rrf_score,
                dense_score=dense_score,
                sparse_score=sparse_score,
                keyword_miss=keyword_miss,
            )
        )

    fused.sort(key=lambda r: r.rrf_score, reverse=True)
    top = fused[:top_k]

    keyword_misses = sum(1 for r in top if r.keyword_miss)
    logger.debug(
        "RRF fusion: %d dense + %d sparse → %d fused (%d keyword-miss)",
        len(dense_results),
        len(sparse_results),
        len(top),
        keyword_misses,
    )

    return top
