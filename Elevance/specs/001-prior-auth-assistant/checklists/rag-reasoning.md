# RAG & Agent Reasoning Quality Checklist

**Purpose**: Validate the quality and completeness of RAG, citation, confidence scoring, and gap analysis requirements.
**Created**: 2026-07-06

## Evidence Retrieval & Fallbacks

- [ ] CHK001 - Are the requirements explicit about the system's behavior when zero relevant evidence is found (e.g., returning "Insufficient Evidence" instead of guessing)? [Coverage, Exception Flow]
- [ ] CHK002 - Are the requirements clear on how the system handles completely contradictory evidence in the clinical notes? [Coverage, Exception Flow]
- [ ] CHK003 - Is the fallback logic for below-threshold confidence scores explicitly defined? [Completeness]

## Citation Metadata & Grounding

- [ ] CHK004 - Does the spec explicitly define the *minimum* required citation metadata (e.g., source document ID, chunk ID, confidence score) for every retrieved claim? [Completeness, Clarity]
- [ ] CHK005 - Is there any ambiguity that could allow the Policy Reasoning agent to generate a summary without a hard link to a source citation? [Ambiguity, Gap]
- [ ] CHK006 - Are requirements for confidence scoring quantified (e.g., threshold values for escalation vs. normal presentation) rather than just stating "high confidence"? [Measurability]

## Gap Analysis Quality

- [ ] CHK007 - Are the requirements for comparing case evidence against medical policy criteria structured to prevent hallucination? [Consistency]
- [ ] CHK008 - Does the gap analysis specification mandate exactly what happens when a policy criterion's presence is "unclear" or "ambiguous"? [Coverage]
- [ ] CHK009 - Is the tone or format of the provider missing-document draft explicitly constrained to remain neutral and objective? [Clarity]

## Architecture Constraints

- [ ] CHK010 - Are the boundaries between the Retrieval Agent (finding facts) and the Reasoning Agent (mapping to policy) explicitly defined to prevent context bleed? [Consistency]
- [ ] CHK011 - Does the spec explicitly prohibit any code path from passing an uncited/unsupported statement to the Reviewer Summary Agent? [Gap]
