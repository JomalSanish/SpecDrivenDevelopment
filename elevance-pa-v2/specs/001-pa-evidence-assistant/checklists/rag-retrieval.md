# RAG / Retrieval Requirements Checklist

**Feature**: `001-pa-evidence-assistant`
**Created**: 2026-07-20
**Checklist Type**: RAG & Retrieval — Requirements Quality Validation
**Purpose**: Validate that requirements governing document extraction, chunking, embedding, hybrid retrieval, the keyword-miss guardrail, OCR fallback gating, and confidence band assignment are complete, unambiguous, consistent, and testable before implementation begins.
**Source documents**: spec.md (FR-011–013, FR-020–025, Constitution Principles V–VIII), data-model.md (Chunk, CompletenessReportItem, Qdrant schema), research.md (§1–4, §8–9), contracts/cases.md

---

## Requirement Completeness

- [ ] CHK001 - Is the chunking strategy (chunk size, overlap, unit of split — sentence vs. token vs. character) explicitly specified as a requirement, or is it left entirely to implementation choice? The research.md mentions "512-token / 50-token overlap" but this appears only as an implementation note, not a normative spec requirement. [Completeness, Gap, research.md §2, data-model.md §documents]
- [ ] CHK002 - Is the OCR near-empty page threshold (the character count below which a page triggers EasyOCR fallback) specified as a requirement? The research.md documents `< 20 stripped characters` but this value is absent from the spec's normative FRs — should it be? [Completeness, Gap, Spec §FR-011, research.md §2]
- [ ] CHK003 - Are requirements defined for how chunking handles page boundaries — specifically, is a chunk ever allowed to span two pages, or must chunks always be contained within a single page so that `page_number` in the Qdrant payload is unambiguous? [Completeness, Gap, data-model.md §Qdrant]
- [ ] CHK004 - Is the embedding dimension (768-dim for nomic-embed-text) specified as a normative requirement in the Qdrant collection schema, so that a dimension mismatch between the embedding model and the vector index is detectable as a configuration error before any documents are indexed? [Completeness, data-model.md §Qdrant, research.md §3]
- [ ] CHK005 - Are requirements defined for the maximum number of chunks retrieved per policy requirement during each retrieval path (dense: top-N, sparse: top-N, RRF output: top-M) — or is the retrieval depth left entirely to the reasoning agent's discretion? [Completeness, Gap, Spec §FR-022–023, research.md §4]
- [ ] CHK006 - Is there a requirement specifying how the system behaves when a document produces zero chunks after extraction — for example, a PDF that passes the `> 20 chars` native-text gate but whose full text is whitespace or control characters? [Completeness, Edge Case, Gap, Spec §FR-020]
- [ ] CHK007 - Are requirements defined for index freshness — specifically, is a case's Qdrant index expected to be fully built before the reasoning agent starts, or can the reasoning agent start against a partially indexed set of chunks? [Completeness, Gap, Spec §FR-020]

---

## Requirement Clarity

- [ ] CHK008 - Is "near-empty text" in FR-011 defined with a concrete, measurable threshold, or does it remain a qualitative descriptor that implementers must interpret independently — creating a risk of inconsistent OCR trigger behavior? [Clarity, Spec §FR-011]
- [ ] CHK009 - Is "confidently identify" in FR-013 (case field extraction) defined with a measurable confidence threshold or a JSON-schema contract that the LLM must satisfy for a field to be considered "found" — or is this entirely delegated to the LLM's internal certainty? [Clarity, Spec §FR-013]
- [ ] CHK010 - Does the spec clarify whether the `extraction_method` chunk provenance field ("native" | "ocr") is set per-page or per-chunk — and if a page is split into multiple chunks, do all chunks from that page inherit the same extraction method? [Clarity, Spec §FR-012, data-model.md §Qdrant]
- [ ] CHK011 - Is the definition of "strong semantic relevance" in the keyword-miss cap rule (FR-023: "top-ranked chunk has strong semantic relevance but zero keyword corroboration") quantified — e.g., what cosine similarity score constitutes "strong"? Without a threshold, the cap rule is untestable. [Clarity, Spec §FR-023, Constitution Principle VIII]
- [ ] CHK012 - Is the term "identifier-bearing requirement" in FR-023 and Principle VIII explicitly defined — which requirement types trigger the keyword-miss cap? The spec introduces `requirement_type` ENUM ('identifier', 'narrative', 'mixed') in the data model, but FR-023 uses different language. Are "identifier" and "mixed" requirement types both subject to the keyword-miss cap, or only "identifier"? [Clarity, Spec §FR-023, data-model.md §policy_requirements]
- [ ] CHK013 - Is the RRF fusion formula (`1/(60+rank)` per path) documented as a normative requirement in the spec, or is it only in research.md as an implementation note — meaning an implementer could substitute a different fusion function and still claim compliance? [Clarity, research.md §4, Spec §FR-023]

---

## Requirement Consistency

- [ ] CHK014 - Are the confidence band thresholds in FR-024 (Present ≥ 85%, Absent < 70%, Unclear 70–84%) consistent with the Constitution Principle VII table (which states "Present ≥85%, Absent <70%, Unclear in between") — and is the boundary value 70.0% itself unambiguously assigned to Absent or Unclear? [Consistency, Spec §FR-024, Constitution Principle VII]
- [ ] CHK015 - Is the `keyword_miss` flag in data-model.md §completeness_report_items consistent with the keyword-miss cap rule in FR-023 — specifically, does the data model capture the original confidence score separately from the capped verdict, so the cap's effect can be audited in the audit log? [Consistency, Spec §FR-023, data-model.md §completeness_report_items]
- [ ] CHK016 - Is the retrieval routing decision (identifier → PostgreSQL; narrative → Qdrant dense; mixed → RRF) consistent between FR-021–023 in the spec, research.md §4, and the `requirement_type` ENUM in the data model — or are there gaps where a requirement type described in one document is not covered in another? [Consistency, Spec §FR-021–023, data-model.md §policy_requirements, research.md §4]
- [ ] CHK017 - Does the requirement that "the pipeline records all intermediate outputs in the audit log" (FR-025) extend to the RRF fusion scores and the keyword-miss cap decision — or only to the final verdict and the reasoning agent's output? Is the scope of "intermediate outputs" sufficiently precise? [Consistency, Spec §FR-025, data-model.md §audit_logs]

---

## Acceptance Criteria Quality

- [ ] CHK018 - Is SC-003 ("pipeline completes within 5 minutes for a typical 3-document case") measurable as written — does "typical" have a defined page count, file size ceiling, or requirement count per policy, so the benchmark is reproducible? [Measurability, Spec §SC-003]
- [ ] CHK019 - Is SC-002 ("AI field extraction correctly identifies at least 4 of 6 targeted fields on a well-structured, native-text clinical note PDF") measurable — is "well-structured" defined, and is the 4/6 threshold measured on a specific fixture document or averaged across a test set? [Measurability, Spec §SC-002]
- [ ] CHK020 - Are there measurable acceptance criteria for the keyword-miss cap specifically — e.g., a scenario where a requirement containing CPT code "72148" is evaluated against a case document that contains the code only in the dense embedding space but not as a literal keyword, and the expected verdict is "Unclear" not "Present"? [Measurability, Gap, Spec §FR-023]
- [ ] CHK021 - Is there a measurable acceptance criterion covering OCR extraction accuracy — e.g., the OCR path must successfully extract a human-readable string from a given scanned-page fixture — or is OCR correctness entirely delegated to EasyOCR's model quality? [Measurability, Gap, Spec §FR-011, Spec §SC-002]

---

## Scenario Coverage

- [ ] CHK022 - Are requirements defined for the case where the same document is uploaded twice to the same case — does the pipeline re-index it (creating duplicate Qdrant points), skip it, or replace the previous index? [Coverage, Gap, Spec §FR-020]
- [ ] CHK023 - Are requirements defined for a policy that has zero saved requirements — what does the completeness pipeline produce for a case linked to such a policy, and does the nurse UI render an empty completeness table or a warning? [Coverage, Gap, Spec §FR-020]
- [ ] CHK024 - Are requirements specified for the reasoning agent's behavior when the retrieved chunks for a narrative requirement are all from OCR-processed pages — is there any additional uncertainty penalty applied, or does the confidence band apply identically regardless of extraction method? [Coverage, Gap, Spec §FR-022, Spec §FR-035]
- [ ] CHK025 - Does the spec define requirements for the embedding model's behavior when a chunk's text exceeds the model's maximum token window (e.g., a very long OCR-produced paragraph) — is truncation required, is chunking expected to prevent this, or is an error returned? [Coverage, Gap, research.md §1]

---

## Edge Case Coverage

- [ ] CHK026 - Is a requirement defined for the OCR fallback's behavior when EasyOCR itself fails on a page (e.g., GPU OOM, corrupted image raster) — the spec's Edge Cases section mentions a `flag indicating extraction failure` but does not define whether this state blocks pipeline progression or allows it to continue with the remaining pages? [Edge Case, Spec §Edge Cases]
- [ ] CHK027 - Is the behavior defined when a policy requirement's `matching_criteria` JSON (for identifier-type requirements) is malformed or empty at pipeline evaluation time — does the pipeline skip the requirement, apply the narrative path, or raise a pipeline error? [Edge Case, Gap, data-model.md §policy_requirements]
- [ ] CHK028 - Does the spec address the scenario where the Qdrant collection is unavailable during pipeline execution (e.g., container restart) — is there a requirement that the pipeline waits, retries, or immediately fails with a `pipeline_error` status? [Edge Case, Gap, Spec §FR-020]
- [ ] CHK029 - Are requirements defined for what constitutes a "valid" Qdrant sparse vector for the BM25 path — specifically, if a chunk has zero non-zero sparse dimensions (e.g., document is very short or entirely stop-words), is it still indexed and included in RRF fusion? [Edge Case, Gap, research.md §3]

---

## Dependencies & Assumptions

- [ ] CHK030 - Is the assumption that "nomic-embed-text and phi4-mini can coexist in 6 GB VRAM simultaneously" validated in any testable requirement — e.g., a startup health-check requirement that confirms both models are loaded before the first pipeline run? [Assumption, research.md §1, Constitution Principle XII]
- [ ] CHK031 - Is the EasyOCR lazy-singleton initialization strategy (model loaded on first OCR trigger, stays in VRAM) documented as a requirement or only as an implementation note — and if VRAM is exhausted by a concurrent LLM call, is a queuing/retry behavior required? [Dependency, Gap, research.md §2]
