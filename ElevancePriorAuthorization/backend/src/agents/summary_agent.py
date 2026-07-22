"""
backend/src/agents/summary_agent.py

summary_agent — Agent 4 of the Five-Agent Architecture.
Implements T021.

Responsibilities:
  1. Accept:
       - The nurse's Reject decision (reason code + free-text notes)
       - The original CompletenessReport (list of ReasoningResult items)
       - Case metadata (member_id, cpt_code, provider_id)
  2. Call the local Ollama LLM to draft a provider-facing missing-document
     communication letter explaining which evidence is absent/unclear and
     what the provider must supply to complete the prior authorization request.
  3. Return the draft as a SummaryAgentResult — always marked DRAFT.

GUARDRAILS (agent-spec.md §4):
  - The draft is NEVER sent directly to the provider.
  - The output is always marked `status="DRAFT"` and must be approved by
    a Nurse or Admin before any downstream delivery action.
  - The agent performs NO clinical assessment — it describes the evidentiary
    gaps identified by the Reasoning Agent only.

Constitution §II: ALL LLM inference goes to the locally-deployed Ollama endpoint
                   sourced via the secrets abstraction — NEVER a public API.
Constitution §I:  This agent ONLY drafts a communication — it cannot record a
                   decision or change the case review_status.

Escalation: If the local Ollama endpoint is unreachable, RuntimeError is raised;
            the draft generation must be retried — no external fallback permitted.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Optional

import httpx

from src.core.secrets import get_secret
from src.models.completeness import CompletenessStatus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


@dataclass
class GapSummaryItem:
    """
    One missing/unclear evidence item to include in the provider communication.
    Derived from CompletenessReportItem rows with status Absent or Unclear.
    """

    requirement_id: str
    requirement_description: str
    status: CompletenessStatus  # Absent or Unclear
    confidence_score: float
    reasoning_summary: str = ""  # Short excerpt from reasoning_log for context


@dataclass
class RejectionContext:
    """
    All inputs needed by the Summary Agent to draft the provider communication.
    """

    # Case identification
    case_id: str
    member_id: str
    provider_id: str
    cpt_code: str

    # Nurse decision
    rejection_reason_code: str  # Structured code, e.g. "MISSING_CLINICAL_NOTES"
    rejection_notes: str  # Free-text nurse notes (may be empty)

    # Gap items (Absent and Unclear completeness items)
    gap_items: list[GapSummaryItem] = field(default_factory=list)


@dataclass
class SummaryAgentResult:
    """
    Draft provider-facing communication produced by the Summary Agent.

    ALWAYS carries status="DRAFT" — must not be delivered without Nurse/Admin approval.
    """

    case_id: str
    draft_communication: str
    status: str = "DRAFT"  # NEVER changed by this agent
    llm_model: str = ""
    llm_endpoint: str = ""
    generation_log: str = ""  # Prompt + raw response for audit trail


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------


def _build_summary_prompt(ctx: RejectionContext) -> str:
    """
    Build the provider-communication drafting prompt.

    The prompt explicitly instructs the model:
      1. To describe missing/unclear evidence items only.
      2. To avoid any clinical language that implies a denial of care.
      3. To use professional, clear language suitable for a provider office.
    """
    gaps_text = ""
    for i, gap in enumerate(ctx.gap_items, start=1):
        status_label = (
            "Missing (not found in submitted documents)"
            if gap.status == CompletenessStatus.Absent
            else "Unclear (insufficient evidence in submitted documents)"
        )
        gaps_text += (
            f"\n{i}. Requirement: {gap.requirement_description}\n"
            f"   Status: {status_label}\n"
        )
        if gap.reasoning_summary:
            gaps_text += f"   Note: {gap.reasoning_summary}\n"

    if not gaps_text:
        gaps_text = "\n[No specific gaps identified — nurse notes contain full context]\n"

    prompt = f"""You are a healthcare administrative assistant drafting a professional
provider communication on behalf of a payer's prior authorization review team.

TASK: Draft a provider-facing letter requesting additional documentation for a
prior authorization request. The letter must:
  1. Be professional, clear, and respectful.
  2. Clearly list each specific document or piece of evidence that is missing
     or insufficient, based on the evidence gaps listed below.
  3. NOT make any clinical recommendation or imply denial of the requested service.
  4. NOT use accusatory or negative language — frame as an information request only.
  5. Be addressed to "Dear Provider" (do not include specific names).
  6. NOT include any personal health information beyond the reference numbers provided.
  7. End with a clear call to action: what the provider should submit and how.

CASE REFERENCE INFORMATION:
  Authorization Request Reference: {ctx.case_id[:8].upper()}
  Member ID: {ctx.member_id}
  Requested Service Code: {ctx.cpt_code}

REVIEWER NOTES:
  Reason Code: {ctx.rejection_reason_code}
  Additional Notes: {ctx.rejection_notes or "(none)"}

EVIDENCE GAPS REQUIRING ADDITIONAL DOCUMENTATION:
{gaps_text}

IMPORTANT: Write ONLY the letter body. Do not include subject line, date, or
sender/recipient addresses — those will be added by the system. Do not add
any preamble, explanation, or markdown. Write the letter in plain paragraphs.

DRAFT LETTER:"""

    return prompt


# ---------------------------------------------------------------------------
# Reviewer Summary & Communication Agent
# ---------------------------------------------------------------------------


class ReviewerSummaryAgent:
    """
    Agent 4: Reviewer Summary & Communication.

    Drafts a provider-facing missing-document communication letter using the
    local Ollama LLM.  The draft is always marked "DRAFT" and cannot be sent
    directly — it requires Nurse/Admin approval (agent-spec.md §4 guardrail).

    Constitution §II: LLM endpoint from secrets abstraction (never hardcoded).
    Constitution §I:  Cannot record a case decision or mutate review_status.
    """

    def __init__(
        self,
        llm_endpoint: Optional[str] = None,
        llm_model: Optional[str] = None,
        http_timeout: float = 120.0,
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
            "ReviewerSummaryAgent initialised: endpoint=%s model=%s timeout=%.1fs",
            self._llm_endpoint,
            self._llm_model,
            self._http_timeout,
        )

    # ------------------------------------------------------------------
    # Internal: LLM call
    # ------------------------------------------------------------------

    async def _call_llm(self, prompt: str, case_id: str) -> str:
        """
        POST to the Ollama /api/generate endpoint.

        Raises RuntimeError if unreachable — no external fallback permitted.
        """
        url = f"{self._llm_endpoint.rstrip('/')}/api/generate"
        payload = {
            "model": self._llm_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.3,   # slightly more natural prose for communications
                "num_predict": 1024,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=self._http_timeout) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                return str(data.get("response", ""))

        except httpx.ConnectError as exc:
            raise RuntimeError(
                f"ReviewerSummaryAgent: Ollama endpoint unreachable at {self._llm_endpoint}. "
                "Draft generation must be retried. No external LLM fallback is permitted. "
                f"Original error: {exc}"
            ) from exc
        except httpx.ReadTimeout as exc:
            raise RuntimeError(
                f"ReviewerSummaryAgent: LLM at {self._llm_endpoint} did not respond within "
                f"{self._http_timeout:.0f} seconds for case_id={case_id}. "
                "Ollama may still be loading the model. Retry after a minute."
            ) from exc
        except httpx.ReadError as exc:
            raise RuntimeError(
                f"ReviewerSummaryAgent: Ollama dropped the connection mid-response for "
                f"case_id={case_id}. Model is likely still loading (cold start). "
                "Retry the case after ~30 seconds, or check 'docker logs pa_ollama'."
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"ReviewerSummaryAgent: Ollama returned HTTP {exc.response.status_code} "
                f"for case_id={case_id}. Original error: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Public: draft communication
    # ------------------------------------------------------------------

    async def draft_communication(
        self,
        ctx: RejectionContext,
    ) -> SummaryAgentResult:
        """
        Draft a provider-facing communication letter for a rejected case.

        The output is always status="DRAFT" — no delivery occurs here.

        Raises RuntimeError if the LLM endpoint is unreachable.
        """
        logger.info(
            "ReviewerSummaryAgent: drafting communication for case_id=%s "
            "gap_items=%d reason_code=%s",
            ctx.case_id,
            len(ctx.gap_items),
            ctx.rejection_reason_code,
        )

        prompt = _build_summary_prompt(ctx)
        raw_response = await self._call_llm(prompt, ctx.case_id)
        draft = raw_response.strip()

        generation_log = json.dumps(
            {
                "prompt_length": len(prompt),
                "raw_response_length": len(raw_response),
                "gap_item_count": len(ctx.gap_items),
                "rejection_reason_code": ctx.rejection_reason_code,
                "llm_model": self._llm_model,
                "llm_endpoint": self._llm_endpoint,
                "draft_status": "DRAFT",
            },
            indent=2,
        )

        logger.info(
            "ReviewerSummaryAgent: draft generated for case_id=%s draft_length=%d",
            ctx.case_id,
            len(draft),
        )

        return SummaryAgentResult(
            case_id=ctx.case_id,
            draft_communication=draft,
            status="DRAFT",  # NEVER changed by this agent (guardrail)
            llm_model=self._llm_model,
            llm_endpoint=self._llm_endpoint,
            generation_log=generation_log,
        )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_agent_instance: Optional[ReviewerSummaryAgent] = None


def get_summary_agent() -> ReviewerSummaryAgent:
    """Return the process-level ReviewerSummaryAgent singleton (lazy init)."""
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = ReviewerSummaryAgent()
    return _agent_instance
