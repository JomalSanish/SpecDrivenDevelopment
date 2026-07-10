"""
backend/src/agents/intake_agent.py

Intake & Classification Agent — Agent 1 of the Five-Agent Architecture.

Responsibilities:
  1. Extract raw text from an uploaded policy PDF (local PyMuPDF / pdfminer).
  2. Send the text to the LOCAL Ollama endpoint to extract a structured list
     of PolicyRequirement items using a few-shot prompt.
  3. Return the parsed list for persistence.

Constitution §II: ALL inference calls go to the locally configured LLM
endpoint (OLLAMA / TEI) — never to any public API. The endpoint URL is
sourced from the secrets abstraction.

Constitution §IV: This agent logs its prompt and model version so every
extraction is auditable (full audit logging wired in Phase 6).
"""
from __future__ import annotations

import json
import logging
import re
import textwrap
from dataclasses import dataclass, field
from typing import Any

import httpx

from src.core.secrets import get_secret

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data transfer objects
# ---------------------------------------------------------------------------


@dataclass
class ExtractedRequirement:
    """A single policy requirement parsed by the agent."""

    description: str
    matching_criteria: dict[str, Any] = field(default_factory=dict)


@dataclass
class IntakeAgentResult:
    """Result returned by the Intake Agent after processing a policy document."""

    requirements: list[ExtractedRequirement]
    raw_text_preview: str  # first 500 chars — for audit logging
    model_used: str
    prompt_tokens_approx: int


# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = textwrap.dedent("""\
    You are a clinical policy analyst. You will be given the text of a payer
    Prior Authorization policy document. Your job is to extract the definitive
    list of required supporting evidence/documents that a provider must submit
    with a prior authorization request for this procedure.

    Output ONLY a valid JSON array (no markdown fences) where each element is:
    {
      "description": "<plain English description of the required evidence>",
      "matching_criteria": {
        "keywords": ["<keyword1>", "<keyword2>"],
        "time_window_months": <integer or null>,
        "notes": "<additional guidance for AI matching>"
      }
    }

    Rules:
    - Each list item MUST correspond to a distinct, independently verifiable
      evidence type (e.g. "Clinical notes from last 6 months" and "Imaging
      necessity documentation" are separate items).
    - Do NOT include meta-requirements like "valid CPT code" — only document
      evidence.
    - If the policy has no explicitly required documents, return an empty
      JSON array [].
    - Do NOT add any text before or after the JSON array.
""")

_FEW_SHOT_USER = textwrap.dedent("""\
    POLICY TEXT:
    MRI Lumbar Spine — Prior Authorization Requirements
    A prior authorization for MRI Lumbar Spine (CPT 72148) requires:
    1. Clinical notes documenting at least 6 weeks of conservative treatment
       (physical therapy or chiropractic care) within the past 6 months.
    2. A signed ordering physician statement establishing medical necessity.
    3. Any prior imaging results relevant to the current complaint (if available).
""")

_FEW_SHOT_ASSISTANT = json.dumps(
    [
        {
            "description": "Clinical notes documenting at least 6 weeks of conservative treatment (physical therapy or chiropractic care) within the past 6 months",
            "matching_criteria": {
                "keywords": ["physical therapy", "chiropractic", "conservative treatment", "6 weeks"],
                "time_window_months": 6,
                "notes": "Look for dated therapy notes or chiropractic records covering a minimum 6-week span.",
            },
        },
        {
            "description": "Signed ordering physician statement establishing medical necessity",
            "matching_criteria": {
                "keywords": ["medical necessity", "physician statement", "ordering physician", "signature"],
                "time_window_months": None,
                "notes": "Must be signed. Unsigned statements do not satisfy this requirement.",
            },
        },
        {
            "description": "Prior imaging results relevant to the current complaint (if available)",
            "matching_criteria": {
                "keywords": ["prior imaging", "X-ray", "CT scan", "MRI", "radiology report"],
                "time_window_months": None,
                "notes": "Optional but should be included if available. Match on radiology report keywords.",
            },
        },
    ],
    indent=2,
)


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class IntakeClassificationAgent:
    """
    Extracts PolicyRequirement items from policy document text.

    Uses the local Ollama HTTP API (OpenAI-compatible /v1/chat/completions).
    Constitution §II: endpoint MUST be the locally configured LLM — never
    a public cloud API.
    """

    def __init__(self) -> None:
        self._endpoint = (get_secret("LLM_ENDPOINT") or "http://localhost:11434").rstrip("/")
        self._model = get_secret("LLM_MODEL") or "llama3"
        self._chat_url = f"{self._endpoint}/v1/chat/completions"
        logger.info(
            "IntakeClassificationAgent initialised: endpoint=%s model=%s",
            self._endpoint,
            self._model,
        )

    async def extract_requirements(self, policy_text: str) -> IntakeAgentResult:
        """
        Send *policy_text* to the local LLM and parse the returned JSON array
        of PolicyRequirement objects.

        Raises RuntimeError if the LLM is unreachable or returns invalid JSON.
        """
        user_message = f"POLICY TEXT:\n{policy_text}"
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            # Few-shot example
            {"role": "user", "content": _FEW_SHOT_USER},
            {"role": "assistant", "content": _FEW_SHOT_ASSISTANT},
            # Actual request
            {"role": "user", "content": user_message},
        ]

        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 2048,
            "stream": False,
        }

        logger.debug(
            "IntakeAgent: sending extraction request to %s (model=%s, text_len=%d)",
            self._chat_url,
            self._model,
            len(policy_text),
        )

        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                response = await client.post(self._chat_url, json=payload)
                response.raise_for_status()
            except httpx.ConnectError as exc:
                raise RuntimeError(
                    f"Intake agent cannot reach local LLM at {self._chat_url}. "
                    "Is Ollama running? (docker-compose up -d ollama)"
                ) from exc
            except httpx.HTTPStatusError as exc:
                raise RuntimeError(
                    f"Intake agent LLM request failed: {exc.response.status_code} "
                    f"{exc.response.text[:300]}"
                ) from exc

        data = response.json()
        content = data["choices"][0]["message"]["content"].strip()

        requirements = self._parse_requirements(content)

        logger.info(
            "IntakeAgent: extracted %d requirements from policy (model=%s)",
            len(requirements),
            self._model,
        )

        return IntakeAgentResult(
            requirements=requirements,
            raw_text_preview=policy_text[:500],
            model_used=self._model,
            prompt_tokens_approx=len(policy_text) // 4,
        )

    @staticmethod
    def _parse_requirements(content: str) -> list[ExtractedRequirement]:
        """Parse the LLM's JSON array response into ExtractedRequirement objects."""
        # Strip optional markdown code fences
        clean = re.sub(r"```(?:json)?", "", content).strip()

        try:
            items = json.loads(clean)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"IntakeAgent: LLM returned invalid JSON: {exc}\n"
                f"Raw content (first 500 chars): {clean[:500]}"
            ) from exc

        if not isinstance(items, list):
            raise RuntimeError(
                f"IntakeAgent: LLM response was JSON but not a list. Got: {type(items)}"
            )

        requirements = []
        for item in items:
            if not isinstance(item, dict) or "description" not in item:
                logger.warning("IntakeAgent: skipping malformed item: %s", item)
                continue
            requirements.append(
                ExtractedRequirement(
                    description=str(item["description"]),
                    matching_criteria=item.get("matching_criteria", {}),
                )
            )

        return requirements


# ---------------------------------------------------------------------------
# Module-level lazy singleton
# ---------------------------------------------------------------------------

_agent_instance: IntakeClassificationAgent | None = None


def get_intake_agent() -> IntakeClassificationAgent:
    """Return the process-level Intake Agent singleton (lazy init)."""
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = IntakeClassificationAgent()
    return _agent_instance
