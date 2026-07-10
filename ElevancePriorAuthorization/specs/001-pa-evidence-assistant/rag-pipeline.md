# RAG Pipeline Specification

## Architecture Overview
The pipeline runs entirely locally, utilizing Qdrant for vector storage and a local embedding service (e.g., TEI running `BAAI/bge-large-en-v1.5`).

## Chunking Strategy
- **Text Splitter**: Semantic sentence-based chunking with overlap.
- **Chunk Size**: 512 tokens.
- **Overlap**: 50 tokens to preserve context across page breaks.
- **Metadata**: Each chunk MUST carry `case_id`, `document_id`, `page_number`, and `chunk_id` (UUID).

## Indexing & Isolation
- All vectors are written to a single Qdrant collection but are **strictly partitioned** using `case_id` as the payload filter during querying.
- A case's documents are indexed immediately post-intake.

## Hybrid Retrieval & Fusion
- **Dense Vector**: 1024-dimension float vector from `bge-large-en`.
- **Sparse Vector**: BM25 tokens extracted natively by Qdrant sparse vectors.
- **Fusion**: Reciprocal Rank Fusion (RRF) is applied to combine dense and sparse candidate lists.
- **Exact-Match Identifier Coverage** (resolves CHK005): Sparse/BM25 vectors are the primary retrieval path for exact-match identifier fields — member ID, CPT/HCPCS codes, ICD-10 codes, and document/section titles. Dense semantic similarity alone MUST NOT be treated as sufficient evidence that an identifier-based requirement is met, since embedding similarity can be high for a *related but wrong* code (e.g., a similar CPT code) while missing the exact string. Any `PolicyRequirement.matching_criteria` that references a specific code or ID MUST instruct the Reasoning Agent to require a sparse/keyword hit on that exact token before it can be scored "Present."

## Dense-Hit / Keyword-Miss Handling (resolves CHK007)
When the fusion step produces a candidate with a strong dense-similarity score but no corresponding sparse/BM25 hit for an identifier-type requirement:
- The Policy Reasoning & Gap Analysis Agent MUST classify the item as **Unclear**, never **Present**, regardless of how high the dense score is.
- The `reasoning_log` on the resulting `CompletenessReportItem` MUST record that this was a dense-hit/keyword-miss case, so the Nurse Reviewer sees why the item needs manual verification rather than a generic "low confidence" note.
- This rule applies only to requirements flagged as identifier-based in `matching_criteria`; free-text clinical requirements (e.g., "clinical notes from last 6 months") are unaffected and continue to use the standard >80% / 50-80% / <50% thresholds.

## Confidence Thresholds
When the Reasoning Agent evaluates the Top-K chunks against a policy requirement, it outputs a score (0-100).
- **Present**: > 80%
- **Unclear**: 50% - 80% (Fuzzy match, requires explicit human verification)
- **Absent**: < 50%
