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

## Confidence Thresholds
When the Reasoning Agent evaluates the Top-K chunks against a policy requirement, it outputs a score (0-100).
- **Present**: > 80%
- **Unclear**: 50% - 80% (Fuzzy match, requires explicit human verification)
- **Absent**: < 50%
