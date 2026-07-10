"""
backend/src/services/pdf_service.py

Local PDF text extraction.
All processing is in-process (no external API calls — constitution §II).

Uses PyMuPDF (fitz) for extraction with pdfminer as a fallback.
Both libraries run entirely locally.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """
    Extract all text from *pdf_bytes* using PyMuPDF (fitz).
    Falls back to pdfminer if PyMuPDF is unavailable.

    Returns plain text. Empty string if no text could be extracted.
    """
    text = _extract_with_pymupdf(pdf_bytes)
    if not text.strip():
        logger.debug("PyMuPDF returned empty text; trying pdfminer fallback.")
        text = _extract_with_pdfminer(pdf_bytes)
    if not text.strip():
        logger.warning("PDF text extraction returned empty content.")
    return text


def _extract_with_pymupdf(pdf_bytes: bytes) -> str:
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages = [page.get_text() for page in doc]
        doc.close()
        return "\n".join(pages)
    except ImportError:
        logger.debug("PyMuPDF (fitz) not installed; skipping.")
        return ""
    except Exception as exc:
        logger.warning("PyMuPDF extraction failed: %s", exc)
        return ""


def _extract_with_pdfminer(pdf_bytes: bytes) -> str:
    try:
        import io
        from pdfminer.high_level import extract_text as pdfminer_extract

        return pdfminer_extract(io.BytesIO(pdf_bytes)) or ""
    except ImportError:
        logger.debug("pdfminer.six not installed; skipping.")
        return ""
    except Exception as exc:
        logger.warning("pdfminer extraction failed: %s", exc)
        return ""
