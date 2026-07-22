"""
backend/src/agents/reasoning_agent.py

reasoning_agent — Agent 3 of the Five-Agent Architecture.
Implements T019 (agent) and T020 (confidence threshold guardrails).

Responsibilities:
  1. Accept a RetrievalAgentResult (fused evidence per requirement) + policy requirements.
  2. For each requirement, call the local Ollama LLM endpoint to assess whether
     the uploaded evidence satisfies the requirement.
  3. Enforce confidence threshold guardrails (T020):
       confidence > 0.80  → Present
       0.50 ≤ conf ≤ 0.80 → Unclear  (forces human review)
       confidence < 0.50  → Absent
     SPECIAL RULE: For identifier-based requirements (member ID, CPT, HCPCS, ICD-10),
     a keyword_miss flag from the Retrieval Agent forces Unclear regardless of
     dense confidence score (per agent-spec.md §Policy Reasoning & Gap Analysis Agent).
  4. Return a list of ReasoningResult objects (one per requirement) that map
     directly to CompletenessReportItem rows.

Constitution §II: ALL LLM inference goes to the locally-deployed Ollama endpoint
                   sourced via the secrets abstraction — NEVER a public API.
Constitution §I:  Results are Present/Absent/Unclear only — no automated decisions.
Constitution §IV: Full prompt + LLM response is captured in reasoning_log.

Escalation: If the local Ollama endpoint is unreachable, RuntimeError is raised
            and the caller must hold the case in queued/retry state with an
            admin-visible alert (per agent-spec.md §3).
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from src.core.secrets import get_secret
from src.models.completeness import CompletenessStatus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Confidence threshold constants (T020)
# ---------------------------------------------------------------------------

THRESHOLD_PRESENT: float = 0.80   # confidence > 0.80  → Present
THRESHOLD_UNCLEAR: float = 0.50   # confidence < 0.50  → Absent


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


@dataclass
class EvidenceChunk:
    """
    A single retrieved evidence chunk passed from the Retrieval Agent.
    Mirrors the relevant fields of FusedResult / TextChunk for decoupling.
    """

    chunk_id: str
    document_id: str
    text: str
    score: float
    keyword_miss: bool = False
    page_number: int = 0


@dataclass
class RequirementContext:
    """
    Full context for one policy requirement passed into the Reasoning Agent.
    """

    requirement_id: str
    description: str
    matching_criteria: dict[str, Any] = field(default_factory=dict)
    is_identifier_based: bool = False
    evidence_chunks: list[EvidenceChunk] = field(default_factory=list)
    keyword_miss_count: int = 0


@dataclass
class ReasoningResult:
    """
    Output of the Reasoning Agent for ONE policy requirement.

    Maps 1-to-1 to a CompletenessReportItem row.

    Fields:
      requirement_id      — UUID of the PolicyRequirement
      status              — System-generated classification (Present/Absent/Unclear)
      confidence_score    — Raw float from LLM response (0.0–1.0)
      matched_document_id — UUID of the best-matching document (may be None if Absent)
      matched_chunk_id    — UUID of the best-matching chunk (may be None if Absent)
      reasoning_log       — Full prompt + LLM response for audit trail (SEC-004)
      keyword_miss_forced — True when Unclear was forced by keyword_miss guardrail
    """

    requirement_id: str
    status: CompletenessStatus
    confidence_score: float
    matched_document_id: Optional[str] = None
    matched_chunk_id: Optional[str] = None
    reasoning_log: str = ""
    keyword_miss_forced: bool = False


@dataclass
class ReasoningAgentResult:
    """Full output of a reasoning run for a case."""

    case_id: str
    results: list[ReasoningResult]
    llm_model: str
    llm_endpoint: str


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------


def _build_reasoning_prompt(
    requirement: RequirementContext,
    evidence_chunks: list[EvidenceChunk],
) -> str:
    """
    Build a few-shot reasoning prompt for the Ollama LLM.

    Asks the model to return a JSON object with:
      {
        "confidence": 0.0-1.0,
        "verdict": "Present" | "Absent" | "Unclear",
        "reasoning": "<one paragraph>"
      }

    The explicit JSON-output instruction is intentional: it allows deterministic
    parsing without brittle string matching.
    """
    evidence_text = ""
    for i, chunk in enumerate(evidence_chunks[:5], start=1):  # top-5 for context window
        evidence_text += (
            f"\n--- Evidence Chunk {i} "
            f"(doc_id={chunk.document_id[:8]}… page={chunk.page_number} "
            f"score={chunk.score:.3f} keyword_miss={chunk.keyword_miss}) ---\n"
            f"{chunk.text[:800]}\n"
        )

    if not evidence_text:
        evidence_text = "\n[No evidence chunks retrieved for this requirement]\n"

    criteria_json = json.dumps(requirement.matching_criteria, indent=2)

    prompt = f"""You are a clinical prior-authorization reviewer assistant.
Your task is to assess whether the submitted case documents satisfy the following policy requirement.
You MUST respond with a single valid JSON object and nothing else.

POLICY REQUIREMENT:
Description: {requirement.description}
Matching Criteria:
{criteria_json}

RETRIEVED EVIDENCE:
{evidence_text}

INSTRUCTIONS:
1. Carefully read the evidence chunks above.
2. Determine whether the evidence CLEARLY satisfies the requirement (Present),
   PARTIALLY or AMBIGUOUSLY satisfies it (Unclear), or is ABSENT/MISSING (Absent).
3. Assign a confidence score between 0.0 and 1.0 reflecting your certainty:
   - 0.0 = completely absent/irrelevant evidence
   - 1.0 = unambiguous, direct evidence present
4. Return ONLY a JSON object with exactly these three keys:
   - "confidence": float between 0.0 and 1.0
   - "verdict": one of "Present", "Absent", "Unclear"
   - "reasoning": a single paragraph explaining your assessment

CRITICAL RULES:
- You MUST NOT recommend accepting or rejecting the authorization request.
- Your role is evidence assessment ONLY.
- If evidence is marginal or ambiguous, use "Unclear" — do not round up to Present.
- Return ONLY the JSON object, no markdown fences or extra text.

JSON RESPONSE:"""

    return prompt


# ---------------------------------------------------------------------------
# Confidence → status mapping (T020 guardrails)
# ---------------------------------------------------------------------------


def apply_confidence_guardrails(
    confidence: float,
    is_identifier_based: bool,
    keyword_miss_count: int,
    parse_failed: bool = False,
) -> tuple[CompletenessStatus, bool]:
    """
    Map a raw confidence score to a CompletenessStatus, enforcing all guardrails.

    T020 Guardrails:
      0. LLM response parse failure → force Unclear (NEVER Absent — a technical
         failure to parse the model's output is not evidence of absence, and
         must not be presented to the nurse as if it were).
      1. confidence > 0.80          → Present
      2. 0.50 ≤ confidence ≤ 0.80   → Unclear (forces human review)
      3. confidence < 0.50          → Absent
      4. Identifier-based + keyword_miss → force Unclear regardless (agent-spec.md §3)

    Returns:
      (CompletenessStatus, keyword_miss_forced: bool)
    """
    # Guardrail 0: parse failure → force Unclear, bypass numeric thresholds entirely
    if parse_failed:
        logger.warning(
            "Guardrail triggered: LLM response parse failure — forcing Unclear "
            "(NOT Absent) regardless of raw confidence=%.3f",
            confidence,
        )
        return CompletenessStatus.Unclear, False

    # Clamp to [0.0, 1.0]
    confidence = max(0.0, min(1.0, float(confidence)))

    # Guardrail: identifier-based requirement with keyword miss → force Unclear
    if is_identifier_based and keyword_miss_count > 0:
        logger.info(
            "Guardrail triggered: identifier-based requirement with %d keyword miss(es) "
            "— forcing Unclear regardless of confidence=%.3f",
            keyword_miss_count,
            confidence,
        )
        return CompletenessStatus.Unclear, True

    # Standard threshold mapping
    if confidence > THRESHOLD_PRESENT:
        return CompletenessStatus.Present, False
    elif confidence >= THRESHOLD_UNCLEAR:
        return CompletenessStatus.Unclear, False
    else:
        return CompletenessStatus.Absent, False


# ---------------------------------------------------------------------------
# LLM response parser
# ---------------------------------------------------------------------------


def _parse_llm_response(raw: str, requirement_id: str) -> tuple[float, str, bool]:
    """
    Parse the LLM JSON response into (confidence, verdict_str, parse_failed).

    On any parse error, returns parse_failed=True. Callers MUST treat
    parse_failed as an explicit override to Unclear — do NOT rely on the
    numeric confidence value alone, since 0.0 falls below THRESHOLD_UNCLEAR
    and would otherwise be (mis)classified as Absent, contradicting the
    fail-safe intent here: a parsing/technical failure is NOT the same as
    "evidence conclusively absent," and must not be presented to the nurse
    as if it were.
    """
    try:
        # Strip potential markdown fences the model might add
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if len(lines) > 2 else text

        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("LLM returned non-object JSON")
        confidence = float(data.get("confidence", 0.0))
        verdict = str(data.get("verdict", "Unclear"))
        return confidence, verdict, False

    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        logger.warning(
            "ReasoningAgent: failed to parse LLM response for req_id=%s: %s — "
            "forcing Unclear (parse_failed=True), NOT Absent",
            requirement_id,
            exc,
        )
        return 0.0, "Unclear", True


# ---------------------------------------------------------------------------
# Policy Reasoning & Gap Analysis Agent
# ---------------------------------------------------------------------------


class PolicyReasoningAgent:
    """
    Agent 3: Policy Reasoning & Gap Analysis.

    Calls the local Ollama LLM endpoint once per policy requirement to assess
    whether the retrieved evidence satisfies the requirement.  Applies the
    confidence threshold guardrails (T020) and returns a list of ReasoningResult
    objects ready for persistence as CompletenessReportItem rows.

    Constitution §II: LLM endpoint is read from the secrets abstraction
                      (never hardcoded or read from os.environ directly).
    Constitution §I:  Outputs Present/Absent/Unclear only — no clinical decisions.
    """

    def __init__(
        self,
        llm_endpoint: Optional[str] = None,
        llm_model: Optional[str] = None,
        http_timeout: float = 900.0,
    ) -> None:
        # Pull endpoint and model from secrets layer (Constitution §V)
        self._llm_endpoint = (
            llm_endpoint
            or get_secret("LLM_ENDPOINT")
            or "http://localhost:11434"
        )
        self._llm_model = (
            llm_model
            or get_secret("LLM_MODEL")
            or "llama3.1"
        )
        self._http_timeout = http_timeout

        logger.info(
            "PolicyReasoningAgent initialised: endpoint=%s model=%s timeout=%.1fs",
            self._llm_endpoint,
            self._llm_model,
            self._http_timeout,
        )

    # ------------------------------------------------------------------
    # Internal: model warm-up
    # ------------------------------------------------------------------

    async def _warm_up_model(self) -> None:
        """
        Send a minimal no-op prompt to the Ollama endpoint to force the model
        into GPU memory before the first real inference request.

        Ollama's cold-start can take 60–180 s depending on model size and
        hardware.  Sending a cheap warm-up prompt (num_predict=1) absorbs that
        latency here rather than timing out mid-pipeline.

        Uses a dedicated generous timeout (360 s) independent of _http_timeout
        so that the warm-up itself can survive the initial model-load period.
        Failures are logged as warnings but do NOT abort the pipeline — the
        subsequent real inference may still succeed if the model loaded in time.
        """
        url = f"{self._llm_endpoint.rstrip('/')}/api/generate"
        payload = {
            "model": self._llm_model,
            "prompt": "ping",
            "stream": False,
            "options": {"num_predict": 1},
        }
        WARMUP_TIMEOUT = 360.0  # seconds — enough for cold-start model load
        try:
            logger.info(
                "ReasoningAgent: warming up model '%s' at %s …",
                self._llm_model,
                self._llm_endpoint,
            )
            async with httpx.AsyncClient(timeout=WARMUP_TIMEOUT) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
            logger.info("ReasoningAgent: model warm-up complete.")
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "ReasoningAgent: warm-up failed (%s) — continuing; "
                "first inference may still timeout if model is not yet loaded.",
                exc,
            )

    # ------------------------------------------------------------------
    # Internal: single LLM call (with retry on timeout)
    # ------------------------------------------------------------------

    async def _call_llm(
        self,
        prompt: str,
        requirement_id: str,
        *,
        max_retries: int = 3,
        retry_delay_s: float = 30.0,
    ) -> str:
        """
        POST to the Ollama /api/generate endpoint.

        Retries up to *max_retries* times on ReadTimeout or ReadError
        (cold-start recovery) with *retry_delay_s* seconds between attempts.

        Raises RuntimeError if the endpoint is unreachable or all retries
        are exhausted (caller must hold the case in queued/retry state —
        no external fallback allowed).

        Returns the raw text content of the model's response.
        """
        url = f"{self._llm_endpoint.rstrip('/')}/api/generate"
        payload = {
            "model": self._llm_model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.1,   # deterministic clinical assessment
                "num_predict": 512,
            },
        }

        last_exc: Exception | None = None
        for attempt in range(1, max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._http_timeout) as client:
                    response = await client.post(url, json=payload)
                    response.raise_for_status()
                    data = response.json()
                    return str(data.get("response", ""))

            except httpx.ConnectError as exc:
                raise RuntimeError(
                    f"PolicyReasoningAgent: Ollama endpoint unreachable at {self._llm_endpoint}. "
                    "Case must be held in queued/retry state. No external LLM fallback is permitted. "
                    f"Original error: {exc}"
                ) from exc
            except (httpx.ReadTimeout, httpx.ReadError) as exc:
                last_exc = exc
                if attempt < max_retries:
                    logger.warning(
                        "ReasoningAgent: LLM timeout/read-error on attempt %d/%d for "
                        "requirement_id=%s (%s). Waiting %.0f s before retry …",
                        attempt,
                        max_retries,
                        requirement_id,
                        type(exc).__name__,
                        retry_delay_s,
                    )
                    await asyncio.sleep(retry_delay_s)
                else:
                    logger.error(
                        "ReasoningAgent: all %d attempts exhausted for requirement_id=%s.",
                        max_retries,
                        requirement_id,
                    )
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code >= 500:
                    last_exc = exc
                    if attempt < max_retries:
                        logger.warning(
                            "ReasoningAgent: LLM returned HTTP %d on attempt %d/%d for "
                            "requirement_id=%s. Waiting %.0f s before retry …",
                            exc.response.status_code,
                            attempt,
                            max_retries,
                            requirement_id,
                            retry_delay_s,
                        )
                        await asyncio.sleep(retry_delay_s)
                    else:
                        logger.error(
                            "ReasoningAgent: all %d attempts exhausted for requirement_id=%s (HTTP %d).",
                            max_retries,
                            requirement_id,
                            exc.response.status_code,
                        )
                else:
                    raise RuntimeError(
                        f"PolicyReasoningAgent: Ollama returned HTTP {exc.response.status_code} "
                        f"for requirement_id={requirement_id}. Original error: {exc}"
                    ) from exc

        # All retries exhausted — re-raise with a clear message
        raise RuntimeError(
            f"PolicyReasoningAgent: LLM at {self._llm_endpoint} did not respond within "
            f"{self._http_timeout:.0f} s after {max_retries} attempt(s) for "
            f"requirement_id={requirement_id}. "
            "Ollama may still be loading the model (cold start). Retry after a minute, "
            "or check 'docker logs pa_ollama'."
        ) from last_exc

    # ------------------------------------------------------------------
    # Internal: assess one requirement
    # ------------------------------------------------------------------

    async def _assess_requirement(
        self, ctx: RequirementContext
    ) -> ReasoningResult:
        """
        Run the full assessment pipeline for a single requirement.

        1. Build prompt from requirement + evidence chunks.
        2. Call LLM.
        3. Parse response.
        4. Apply confidence guardrails (T020).
        5. Return ReasoningResult.
        """
        prompt = _build_reasoning_prompt(ctx, ctx.evidence_chunks)

        logger.debug(
            "ReasoningAgent: calling LLM for requirement_id=%s evidence_chunks=%d",
            ctx.requirement_id,
            len(ctx.evidence_chunks),
        )

        raw_response = await self._call_llm(prompt, ctx.requirement_id)
        confidence, _, parse_failed = _parse_llm_response(raw_response, ctx.requirement_id)

        # T020 guardrails
        status, keyword_miss_forced = apply_confidence_guardrails(
            confidence=confidence,
            is_identifier_based=ctx.is_identifier_based,
            keyword_miss_count=ctx.keyword_miss_count,
            parse_failed=parse_failed,
        )

        # Best-match citation (top-scored chunk that is not keyword_miss, else top overall)
        best_chunk = None
        non_miss_chunks = [c for c in ctx.evidence_chunks if not c.keyword_miss]
        if non_miss_chunks:
            best_chunk = max(non_miss_chunks, key=lambda c: c.score)
        elif ctx.evidence_chunks:
            best_chunk = max(ctx.evidence_chunks, key=lambda c: c.score)

        matched_document_id = best_chunk.document_id if best_chunk else None
        matched_chunk_id = best_chunk.chunk_id if best_chunk else None

        # Reasoning log for audit trail (SEC-004)
        reasoning_log = json.dumps(
            {
                "prompt_length": len(prompt),
                "llm_raw_response": raw_response[:2000],  # truncate for storage
                "parsed_confidence": confidence,
                "parse_failed": parse_failed,
                "applied_status": status.value,
                "keyword_miss_forced": keyword_miss_forced,
                "evidence_chunk_count": len(ctx.evidence_chunks),
                "keyword_miss_count": ctx.keyword_miss_count,
                "is_identifier_based": ctx.is_identifier_based,
                "llm_model": self._llm_model,
                "llm_endpoint": self._llm_endpoint,
            },
            indent=2,
        )

        logger.info(
            "ReasoningAgent: req_id=%s confidence=%.3f status=%s keyword_miss_forced=%s",
            ctx.requirement_id,
            confidence,
            status.value,
            keyword_miss_forced,
        )

        return ReasoningResult(
            requirement_id=ctx.requirement_id,
            status=status,
            confidence_score=confidence,
            matched_document_id=matched_document_id,
            matched_chunk_id=matched_chunk_id,
            reasoning_log=reasoning_log,
            keyword_miss_forced=keyword_miss_forced,
        )

    # ------------------------------------------------------------------
    # Public: assess all requirements for a case
    # ------------------------------------------------------------------

    async def assess(
        self,
        case_id: str,
        requirement_contexts: list[RequirementContext],
    ) -> ReasoningAgentResult:
        """
        Run the completeness assessment pipeline for all requirements in a case.

        Processes requirements sequentially (shared LLM endpoint; parallel
        requests would saturate a single Ollama instance).

        Returns a ReasoningAgentResult with one ReasoningResult per requirement.

        Raises RuntimeError if the LLM endpoint is unreachable (no external
        fallback — caller holds the case in queued/retry state).
        """
        logger.info(
            "ReasoningAgent: starting assessment for case_id=%s, %d requirements",
            case_id,
            len(requirement_contexts),
        )

        # Warm up the model before the first real inference to absorb cold-start
        # latency (model load can take 60–180 s on first call).
        await self._warm_up_model()

        results: list[ReasoningResult] = []
        for ctx in requirement_contexts:
            result = await self._assess_requirement(ctx)
            results.append(result)

        present_count = sum(1 for r in results if r.status == CompletenessStatus.Present)
        unclear_count = sum(1 for r in results if r.status == CompletenessStatus.Unclear)
        absent_count = sum(1 for r in results if r.status == CompletenessStatus.Absent)

        logger.info(
            "ReasoningAgent: assessment complete for case_id=%s — "
            "Present=%d Unclear=%d Absent=%d",
            case_id,
            present_count,
            unclear_count,
            absent_count,
        )

        return ReasoningAgentResult(
            case_id=case_id,
            results=results,
            llm_model=self._llm_model,
            llm_endpoint=self._llm_endpoint,
        )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_agent_instance: Optional[PolicyReasoningAgent] = None


def get_reasoning_agent() -> PolicyReasoningAgent:
    """Return the process-level PolicyReasoningAgent singleton (lazy init)."""
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = PolicyReasoningAgent()
    return _agent_instance
