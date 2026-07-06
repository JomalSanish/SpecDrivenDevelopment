# RAG Pipeline Specification: Prior Authorization Evidence Assistant

## 1. Document Chunking Strategy
- **Medical Policy Documents**: Chunked strictly by semantic section headers (e.g., "Coverage Criteria", "Exclusions"). If a section exceeds context limits, sub-chunk by paragraphs while retaining the parent section header as context.
- **Clinical Notes & Provider Submissions**: Chunked by clinical paragraph or list item. Extracted text from the OCR placeholder should preserve newline and structural boundaries (e.g., "History of Present Illness", "Plan").

## 2. Embedding Generation & Storage
- **Model**: Swappable embedding provider interface (e.g., text-embedding-3-small or equivalent), stored in `pgvector`.
- **Refresh Strategy**: 
  - Medical policies are embedded at the time of ingestion/update.
  - Case attachments are embedded asynchronously upon upload and linked to the `case_id`.

## 3. Hybrid Search Approach
- **Vector Index**: Postgres 16 with `pgvector` for semantic similarity.
- **Keyword Search**: Postgres Full-Text Search (FTS) using `tsvector`.
- **Fusion**: Reciprocal Rank Fusion (RRF) combines semantic and keyword scores to ensure exact clinical term matches (e.g., specific drug names, CPT codes) are prioritized alongside conceptual matches (e.g., "conservative therapy").

## 4. Citation Format & Confidence Scoring
- **Citation Format**: Every retrieved chunk must return a `citation_ref` linking to the original document UUID and page/section number. The UI will render this as `[Source Name, p. X]`.
- **Confidence Scoring Method**: 
  - Calculated as a normalized combination of the RRF retrieval score and the LLM's self-assessed relevance score (0.0 to 1.0).
  - **Thresholds**:
    - `< 0.6`: Auto-flag for manual review (low confidence).
    - `0.6 - 0.8`: Surface with caution indicator (yellow).
    - `> 0.8`: Present normally (green).

## 5. Safe Failure Modes
- **Explicit Fallback**: If the maximum confidence score for a query is below 0.3, the RAG agent MUST short-circuit and return a status of `"Insufficient Evidence"` rather than attempting to prompt the LLM. Hallucination prevention is paramount.

## 6. Contradictory Evidence Detection
- During the Policy Reasoning phase, the prompt explicitly instructs the LLM to analyze the retrieved `EvidenceItem` array for conflicts (e.g., Chunk A states "6 months PT completed" while Chunk B states "No prior conservative therapy").
- If detected, the agent sets `conflict_detected = true` and `status = unclear`, forcing the routing logic to escalate to the Medical Director queue.
