"""
backend/src/services/chunking_service.py

Semantic sentence-based text chunking for the PA Evidence RAG pipeline.

Specification (rag-pipeline.md §Chunking Strategy):
  - Text Splitter : Semantic sentence-based with overlap
  - Chunk Size    : 512 tokens
  - Overlap       : 50 tokens (preserve context across page breaks)
  - Metadata      : Each chunk MUST carry case_id, document_id,
                    page_number, and chunk_id (UUID)

All processing is in-process (no network calls — Constitution §II).
"""
from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CHUNK_SIZE_TOKENS = 512
OVERLAP_TOKENS = 50

# Simple whitespace-based tokenisation approximation:
# ~4 characters per token (GPT-2 / BPE average for English medical text)
_CHARS_PER_TOKEN = 4
CHUNK_SIZE_CHARS = CHUNK_SIZE_TOKENS * _CHARS_PER_TOKEN   # 2048 chars
OVERLAP_CHARS = OVERLAP_TOKENS * _CHARS_PER_TOKEN          # 200 chars

# Sentence boundary pattern: split on ". ", "! ", "? ", newlines
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+|\n{2,}")


# ---------------------------------------------------------------------------
# Output data class
# ---------------------------------------------------------------------------


@dataclass
class TextChunk:
    """
    A single chunk of extracted text ready for embedding and indexing.

    Fields mirror rag-pipeline.md §Chunking Strategy metadata requirements:
      case_id      — UUID of the PA case
      document_id  — UUID of the source document
      chunk_id     — stable UUID assigned at chunk time
      page_number  — 0-based page the chunk originated from
      text         — the chunk text content
      token_count  — approximate token count for this chunk
    """

    case_id: str
    document_id: str
    chunk_id: str
    page_number: int
    text: str
    token_count: int


# ---------------------------------------------------------------------------
# Core chunking logic
# ---------------------------------------------------------------------------


def _estimate_tokens(text: str) -> int:
    """Approximate token count using character-based heuristic."""
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _split_into_sentences(text: str) -> list[str]:
    """
    Split *text* into a list of sentence strings.
    Preserves sentence-internal whitespace; trims only leading/trailing space.
    """
    raw = _SENTENCE_BOUNDARY.split(text)
    return [s.strip() for s in raw if s.strip()]


def _build_chunks(sentences: list[str]) -> list[str]:
    """
    Pack *sentences* into overlapping chunks of ~CHUNK_SIZE_TOKENS tokens
    with OVERLAP_TOKENS of carry-over context.

    Algorithm:
    1. Accumulate sentences into the current chunk buffer.
    2. When the buffer exceeds CHUNK_SIZE_TOKENS, flush the chunk.
    3. Seed the next chunk with the last OVERLAP_TOKENS worth of text from
       the flushed chunk (overlap window).
    """
    if not sentences:
        return []

    chunks: list[str] = []
    current_sentences: list[str] = []
    current_tokens = 0

    for sentence in sentences:
        sent_tokens = _estimate_tokens(sentence)

        # If a single sentence exceeds chunk size, split it by character limit
        if sent_tokens > CHUNK_SIZE_TOKENS:
            # Flush current buffer first
            if current_sentences:
                chunks.append(" ".join(current_sentences))
                current_sentences = []
                current_tokens = 0
            # Hard-split the oversized sentence
            for sub in _hard_split(sentence):
                chunks.append(sub)
            continue

        # Adding this sentence would exceed the limit — flush
        if current_tokens + sent_tokens > CHUNK_SIZE_TOKENS and current_sentences:
            chunk_text = " ".join(current_sentences)
            chunks.append(chunk_text)

            # Overlap: seed next chunk with tail sentences
            overlap_text = _tail_by_tokens(current_sentences, OVERLAP_TOKENS)
            current_sentences = [overlap_text] if overlap_text else []
            current_tokens = _estimate_tokens(overlap_text) if overlap_text else 0

        current_sentences.append(sentence)
        current_tokens += sent_tokens

    # Flush final chunk
    if current_sentences:
        chunks.append(" ".join(current_sentences))

    return chunks


def _hard_split(text: str) -> list[str]:
    """Split a single oversized text string into CHUNK_SIZE_CHARS segments."""
    parts = []
    for i in range(0, len(text), CHUNK_SIZE_CHARS - OVERLAP_CHARS):
        part = text[i : i + CHUNK_SIZE_CHARS]
        if part.strip():
            parts.append(part.strip())
    return parts


def _tail_by_tokens(sentences: list[str], target_tokens: int) -> str:
    """
    Return the trailing portion of *sentences* that fits within *target_tokens*.
    """
    tail: list[str] = []
    accumulated = 0
    for sentence in reversed(sentences):
        t = _estimate_tokens(sentence)
        if accumulated + t > target_tokens:
            break
        tail.insert(0, sentence)
        accumulated += t
    return " ".join(tail)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def chunk_text(
    text: str,
    case_id: str,
    document_id: str,
    page_number: int = 0,
) -> list[TextChunk]:
    """
    Split *text* into overlapping semantic chunks and attach required metadata.

    Parameters
    ----------
    text        : The plain text to chunk (already extracted from a PDF page).
    case_id     : UUID of the PA case — stamped on every chunk.
    document_id : UUID of the source Document row — stamped on every chunk.
    page_number : 0-based page number the text came from.

    Returns
    -------
    List of TextChunk objects, one per chunk.  Returns empty list for blank
    or whitespace-only input.
    """
    text = text.strip()
    if not text:
        return []

    sentences = _split_into_sentences(text)
    raw_chunks = _build_chunks(sentences)

    result: list[TextChunk] = []
    for raw in raw_chunks:
        if not raw.strip():
            continue
        result.append(
            TextChunk(
                case_id=case_id,
                document_id=document_id,
                chunk_id=str(uuid.uuid4()),
                page_number=page_number,
                text=raw,
                token_count=_estimate_tokens(raw),
            )
        )

    logger.debug(
        "Chunked document_id=%s page=%d → %d chunks",
        document_id,
        page_number,
        len(result),
    )
    return result


def chunk_pages(
    pages: list[str],
    case_id: str,
    document_id: str,
) -> list[TextChunk]:
    """
    Chunk a multi-page document.

    *pages* is a list of page-level text strings (index 0 = page 1).
    Chunks from different pages share the same case_id and document_id
    but carry the correct page_number.

    Returns all chunks across all pages in page order.
    """
    all_chunks: list[TextChunk] = []
    for page_idx, page_text in enumerate(pages):
        page_chunks = chunk_text(
            text=page_text,
            case_id=case_id,
            document_id=document_id,
            page_number=page_idx,
        )
        all_chunks.extend(page_chunks)

    logger.info(
        "Chunked %d page(s) for document_id=%s → %d total chunks",
        len(pages),
        document_id,
        len(all_chunks),
    )
    return all_chunks
