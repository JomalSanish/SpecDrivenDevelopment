"""
backend/src/services/completeness_pipeline.py

Orchestrates the full completeness check pipeline for a newly submitted case:

  1. Load documents and case from DB
  2. Download each document from MinIO, extract text via pdf_service
  3. Chunk text (chunk_pages from chunking_service)
  4. Index chunks into Qdrant per document (qdrant_service.index_text_chunks)
  5. For each policy requirement, hybrid search (dense + sparse)
  6. Fuse results via RRF (fusion_service.reciprocal_rank_fusion)
  7. Run the Reasoning Agent to assess each requirement
  8. Persist CompletenessReportItem rows
  9. Advance case.review_status → in_nurse_review, set entered_review_at

Constitution constraints:
  §I  — No automated clinical decisions; only status advancement to human review queue.
  §II — All inference (embedding, LLM) uses local endpoints via secrets abstraction.
  §IV — Full reasoning log stored per requirement for auditability.
"""
from __future__ import annotations

import io
import logging
import uuid
from datetime import datetime, timezone

from minio import Minio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import AsyncSessionLocal
from src.core.secrets import get_secret, require_secret
from src.models.case import Case, Document, ReviewStatus
from src.models.completeness import CompletenessReportItem
from src.models.policy import PolicyRequirement
from src.services.chunking_service import chunk_pages
from src.services.fusion_service import reciprocal_rank_fusion
from src.services.pdf_service import extract_text_from_pdf
from src.services.qdrant_service import get_qdrant_service
from src.agents.reasoning_agent import (
    EvidenceChunk,
    RequirementContext,
    get_reasoning_agent,
)

logger = logging.getLogger(__name__)

# Top-K chunks to retrieve per requirement per search type (dense + sparse)
RETRIEVAL_TOP_K = 10
# How many fused results to pass to the reasoning agent
REASONING_TOP_K = 5


def _get_minio_client() -> Minio:
    """Lazy MinIO client using secrets abstraction (Constitution §V)."""
    endpoint = require_secret("MINIO_ENDPOINT")
    access_key = require_secret("MINIO_ACCESS_KEY")
    secret_key = require_secret("MINIO_SECRET_KEY")
    secure = (get_secret("MINIO_SECURE") or "false").lower() == "true"
    return Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)


def _download_bytes(object_key: str) -> bytes:
    """Download a document from MinIO and return raw bytes."""
    client = _get_minio_client()
    bucket = get_secret("MINIO_BUCKET") or "pa-case-documents"
    response = client.get_object(bucket, object_key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


async def run_completeness_pipeline(case_id: str) -> None:
    """
    Run the full completeness check pipeline for *case_id*.

    Creates its own DB session (designed to run as a background task after the
    HTTP response for case creation has already been sent).

    On failure: logs the error; the case stays in 'pending_verification' so
    operations staff can see it stalled (FR-014 — no silent drop).
    """
    logger.info("Completeness pipeline starting for case_id=%s", case_id)

    async with AsyncSessionLocal() as db:
        try:
            await _run(db, case_id)
            await db.commit()
            logger.info("Completeness pipeline complete for case_id=%s", case_id)
        except Exception as exc:
            await db.rollback()
            logger.error(
                "Completeness pipeline FAILED for case_id=%s: %s",
                case_id,
                exc,
                exc_info=True,
            )
            # Case intentionally left in pending_verification — visible to ops.


async def _run(db: AsyncSession, case_id: str) -> None:
    case_uuid = uuid.UUID(case_id)

    # ------------------------------------------------------------------
    # 1. Load case + policy requirements
    # ------------------------------------------------------------------
    case_result = await db.execute(select(Case).where(Case.id == case_uuid))
    case = case_result.scalar_one_or_none()
    if case is None:
        raise RuntimeError(f"Case {case_id} not found in DB")

    req_result = await db.execute(
        select(PolicyRequirement).where(PolicyRequirement.policy_id == case.policy_id)
    )
    requirements = req_result.scalars().all()

    if not requirements:
        logger.warning(
            "No policy requirements found for policy_id=%s — advancing case directly.",
            case.policy_id,
        )
        _advance_to_nurse_review(case)
        return

    # ------------------------------------------------------------------
    # 2. Load documents and index their text into Qdrant
    # ------------------------------------------------------------------
    doc_result = await db.execute(
        select(Document).where(Document.case_id == case_uuid)
    )
    documents = doc_result.scalars().all()

    qdrant = get_qdrant_service()
    await qdrant.ensure_collection()

    for doc in documents:
        try:
            file_bytes = _download_bytes(doc.storage_path)
        except Exception as exc:
            logger.warning(
                "Could not download document %s from MinIO: %s — skipping.", doc.id, exc
            )
            continue

        # extract_text_from_pdf returns all page text concatenated.
        # We treat the whole document as a single "page" for simplicity;
        # chunk_pages handles multi-page splitting internally.
        full_text = extract_text_from_pdf(file_bytes)
        if not full_text.strip():
            logger.warning("Document %s yielded no text — skipping.", doc.id)
            continue

        # Split into pages on form-feed or double-newline to pass per-page texts
        import re
        raw_pages = re.split(r"\f|\n{3,}", full_text)
        pages = [p for p in raw_pages if p.strip()] or [full_text]

        # ------------------------------------------------------------------
        # 3+4. Chunk + index into Qdrant
        # ------------------------------------------------------------------
        chunks = chunk_pages(
            pages=pages,
            case_id=str(case_uuid),
            document_id=str(doc.id),
        )

        chunk_texts = [c.text for c in chunks]
        page_numbers = [c.page_number for c in chunks]

        if chunk_texts:
            indexed = await qdrant.index_text_chunks(
                case_id=str(case_uuid),
                document_id=str(doc.id),
                texts=chunk_texts,
                page_numbers=page_numbers,
            )
            logger.info("Indexed %d chunks for document %s.", indexed, doc.id)

    # ------------------------------------------------------------------
    # 5+6+7. Per requirement: hybrid retrieve → fuse → reason
    # ------------------------------------------------------------------
    reasoning_agent = get_reasoning_agent()
    requirement_contexts: list[RequirementContext] = []

    for req in requirements:
        dense_results = await qdrant.search_dense(
            query_text=req.description,
            case_id=str(case_uuid),
            top_k=RETRIEVAL_TOP_K,
        )
        sparse_results = await qdrant.search_sparse(
            query_text=req.description,
            case_id=str(case_uuid),
            top_k=RETRIEVAL_TOP_K,
        )
        fused = reciprocal_rank_fusion(
            dense_results=dense_results,
            sparse_results=sparse_results,
            top_k=REASONING_TOP_K,
        )

        criteria = req.matching_criteria or {}
        is_identifier = bool(criteria.get("identifier_based", False))

        evidence_chunks = [
            EvidenceChunk(
                chunk_id=f.chunk_id,
                document_id=f.document_id,
                text=f.text,
                score=f.rrf_score,
                keyword_miss=f.keyword_miss,
                page_number=f.page_number,
            )
            for f in fused
        ]

        requirement_contexts.append(
            RequirementContext(
                requirement_id=str(req.id),
                description=req.description,
                evidence_chunks=evidence_chunks,
                keyword_miss_count=sum(1 for e in evidence_chunks if e.keyword_miss),
                is_identifier_based=is_identifier,
            )
        )

    agent_result = await reasoning_agent.assess(
        case_id=case_id,
        requirement_contexts=requirement_contexts,
    )

    # ------------------------------------------------------------------
    # 8. Persist CompletenessReportItem rows
    # ------------------------------------------------------------------
    for result in agent_result.results:
        item = CompletenessReportItem(
            case_id=case_uuid,
            policy_requirement_id=uuid.UUID(result.requirement_id),
            status=result.status,
            confidence_score=result.confidence_score,
            matched_document_id=(
                uuid.UUID(result.matched_document_id)
                if result.matched_document_id
                else None
            ),
            matched_chunk_id=(
                uuid.UUID(result.matched_chunk_id)
                if result.matched_chunk_id
                else None
            ),
            reasoning_log=result.reasoning_log,
        )
        db.add(item)

    # ------------------------------------------------------------------
    # 9. Advance case to nurse review (FR-004, constitution §I)
    # ------------------------------------------------------------------
    _advance_to_nurse_review(case)


def _advance_to_nurse_review(case: Case) -> None:
    """Set review_status → in_nurse_review and stamp entered_review_at."""
    case.review_status = ReviewStatus.in_nurse_review
    case.entered_review_at = datetime.now(timezone.utc)
    logger.info(
        "Case %s advanced to in_nurse_review at %s.", case.id, case.entered_review_at
    )
