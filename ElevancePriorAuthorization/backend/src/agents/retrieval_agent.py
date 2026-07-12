"""
backend/src/agents/retrieval_agent.py

Evidence Retrieval (RAG) Agent — Agent 2 of the Five-Agent Architecture.

Responsibilities:
  1. Accept a `case_id` and a list of `PolicyRequirement` matching queries.
  2. Run hybrid retrieval for each requirement:
       a. Dense semantic search (via QdrantIndexingService.search_dense)
       b. Sparse BM25 keyword search (via QdrantIndexingService.search_sparse)
       c. Reciprocal Rank Fusion (via fusion_service.reciprocal_rank_fusion)
  3. Return a structured RetrievalResult per requirement, including the
     `keyword_miss` flag for every fused candidate so the Reasoning Agent
     (T019) can enforce the Dense-Hit / Keyword-Miss guardrail.

Constitution §II: ALL inference (embedding) goes through the locally-deployed
TEI endpoint via QdrantIndexingService — never a public API.

Constitution §IV: Every retrieval action is logged with enough detail for
audit reconstruction (full audit logging wired in Phase 6 / T030).

rag-pipeline.md §Exact-Match Identifier Coverage:
  Any PolicyRequirement whose matching_criteria references a specific code
  or ID MUST rely on sparse/BM25 hit as the primary signal.  This is
  enforced by the `keyword_miss` flag propagated from FusedResult.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from src.core.secrets import get_secret
from src.services.chunking_service import chunk_pages
from src.services.fusion_service import FusedResult, reciprocal_rank_fusion
from src.services.qdrant_service import (
    QdrantIndexingService,
    get_qdrant_service,
)

logger = logging.getLogger(__name__)

# Default top-k per search leg before RRF
DEFAULT_SEARCH_TOP_K = 20
# Top-k results returned to the Reasoning Agent after fusion
DEFAULT_FUSED_TOP_K = 10


# ---------------------------------------------------------------------------
# Data transfer objects
# ---------------------------------------------------------------------------


@dataclass
class RequirementQuery:
    """
    A single policy requirement query sent to the retrieval agent.

    Fields:
      requirement_id       — UUID of the PolicyRequirement row
      description          — human-readable requirement text
      matching_criteria    — JSON from policy parsing; drives query construction
      is_identifier_based  — True when the requirement involves exact codes/IDs
                             (member ID, CPT, HCPCS, ICD-10). Controls whether
                             the keyword_miss guardrail applies in the Reasoning Agent.
    """

    requirement_id: str
    description: str
    matching_criteria: dict[str, Any] = field(default_factory=dict)
    is_identifier_based: bool = False


@dataclass
class RequirementEvidence:
    """
    Retrieved evidence for ONE policy requirement.

    fused_results — top-k fused candidates (dense + sparse via RRF)
    keyword_miss_count — number of fused results that are dense-hit/keyword-miss
                         (non-zero = Reasoning Agent must scrutinise carefully)
    """

    requirement_id: str
    description: str
    is_identifier_based: bool
    fused_results: list[FusedResult]
    keyword_miss_count: int


@dataclass
class RetrievalAgentResult:
    """Full output of a retrieval run for a case."""

    case_id: str
    evidence: list[RequirementEvidence]
    model_used: str  # embedding model/endpoint for audit
    retrieval_top_k: int


# ---------------------------------------------------------------------------
# Query construction
# ---------------------------------------------------------------------------


def _build_query_text(req: RequirementQuery) -> str:
    """
    Build a retrieval query string from a RequirementQuery.

    Combines the requirement description with keywords from matching_criteria
    so both the dense and sparse legs are maximally informed.
    """
    parts = [req.description]
    criteria = req.matching_criteria

    keywords = criteria.get("keywords", [])
    if keywords:
        parts.append(" ".join(str(k) for k in keywords))

    notes = criteria.get("notes", "")
    if notes:
        parts.append(notes)

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Evidence Retrieval Agent
# ---------------------------------------------------------------------------


class EvidenceRetrievalAgent:
    """
    Hybrid RAG retrieval agent.

    Runs dense + sparse retrieval in parallel for each policy requirement
    and fuses results via RRF.  Propagates keyword_miss flags to support
    the Dense-Hit / Keyword-Miss guardrail in the downstream Reasoning Agent.

    Constitution §II: All embedding inference is local (TEI endpoint sourced
    from secrets abstraction via QdrantIndexingService).
    """

    def __init__(
        self,
        qdrant_service: Optional[QdrantIndexingService] = None,
        search_top_k: int = DEFAULT_SEARCH_TOP_K,
        fused_top_k: int = DEFAULT_FUSED_TOP_K,
    ) -> None:
        self._qdrant = qdrant_service or get_qdrant_service()
        self._search_top_k = search_top_k
        self._fused_top_k = fused_top_k
        # Embedding endpoint for audit logging
        self._embedding_endpoint = (
            get_secret("EMBEDDING_ENDPOINT") or "http://localhost:8080"
        )
        logger.info(
            "EvidenceRetrievalAgent initialised: embedding=%s search_top_k=%d fused_top_k=%d",
            self._embedding_endpoint,
            self._search_top_k,
            self._fused_top_k,
        )

    async def retrieve(
        self,
        case_id: str,
        requirements: list[RequirementQuery],
    ) -> RetrievalAgentResult:
        """
        Run hybrid RAG retrieval for all *requirements* scoped to *case_id*.

        Returns a RetrievalAgentResult with one RequirementEvidence per
        requirement, sorted by requirement order.

        Raises RuntimeError if Qdrant or the embedding service is unreachable.
        """
        logger.info(
            "RetrievalAgent: retrieving evidence for case_id=%s, %d requirements",
            case_id,
            len(requirements),
        )

        evidence_list: list[RequirementEvidence] = []

        for req in requirements:
            query_text = _build_query_text(req)
            logger.debug(
                "RetrievalAgent: querying for requirement_id=%s query_len=%d",
                req.requirement_id,
                len(query_text),
            )

            # Run both search legs
            dense_results = await self._qdrant.search_dense(
                query_text=query_text,
                case_id=case_id,
                top_k=self._search_top_k,
            )
            sparse_results = await self._qdrant.search_sparse(
                query_text=query_text,
                case_id=case_id,
                top_k=self._search_top_k,
            )

            # Fuse
            fused = reciprocal_rank_fusion(
                dense_results=dense_results,
                sparse_results=sparse_results,
                top_k=self._fused_top_k,
            )

            keyword_miss_count = sum(1 for r in fused if r.keyword_miss)

            if keyword_miss_count > 0:
                logger.warning(
                    "RetrievalAgent: %d keyword-miss result(s) for requirement_id=%s "
                    "(is_identifier_based=%s). Reasoning Agent must treat these as "
                    "at most Unclear for identifier requirements.",
                    keyword_miss_count,
                    req.requirement_id,
                    req.is_identifier_based,
                )

            evidence_list.append(
                RequirementEvidence(
                    requirement_id=req.requirement_id,
                    description=req.description,
                    is_identifier_based=req.is_identifier_based,
                    fused_results=fused,
                    keyword_miss_count=keyword_miss_count,
                )
            )

        logger.info(
            "RetrievalAgent: completed retrieval for case_id=%s — %d requirements processed",
            case_id,
            len(evidence_list),
        )

        return RetrievalAgentResult(
            case_id=case_id,
            evidence=evidence_list,
            model_used=self._embedding_endpoint,
            retrieval_top_k=self._fused_top_k,
        )

    async def index_case_document(
        self,
        case_id: str,
        document_id: str,
        pages: list[str],
    ) -> int:
        """
        Convenience entry-point: chunk *pages* and index into Qdrant.

        Calls chunking_service.chunk_pages() then
        QdrantIndexingService.index_text_chunks() for each page.

        Returns total number of indexed chunks.
        """
        await self._qdrant.ensure_collection()

        all_chunks = chunk_pages(
            pages=pages,
            case_id=case_id,
            document_id=document_id,
        )

        if not all_chunks:
            logger.warning(
                "RetrievalAgent: no chunks produced for document_id=%s (empty document?)",
                document_id,
            )
            return 0

        # Index in a single batch (all chunks already have vectors computed below)
        texts = [c.text for c in all_chunks]
        page_numbers = [c.page_number for c in all_chunks]

        indexed = await self._qdrant.index_text_chunks(
            case_id=case_id,
            document_id=document_id,
            texts=texts,
            page_numbers=page_numbers,
        )

        logger.info(
            "RetrievalAgent: indexed %d chunks for case_id=%s document_id=%s",
            indexed,
            case_id,
            document_id,
        )
        return indexed


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_agent_instance: Optional[EvidenceRetrievalAgent] = None


def get_retrieval_agent() -> EvidenceRetrievalAgent:
    """Return the process-level EvidenceRetrievalAgent singleton (lazy init)."""
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = EvidenceRetrievalAgent()
    return _agent_instance
