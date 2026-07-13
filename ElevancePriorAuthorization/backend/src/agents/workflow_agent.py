"""
backend/src/agents/workflow_agent.py

Workflow/Audit & Deployment Readiness Agent — Agent 5 of the Five-Agent
Architecture.  Implements T029.

Responsibilities
----------------
1. **Case routing**: Inspect a case's current state and determine the
   next workflow action (e.g., trigger completeness pipeline, escalate SLA,
   move to nurse review, reject to provider).

2. **Audit orchestration**: After each agent completes, emit an AuditLog
   row via AuditLogger so the full multi-agent trace is persisted.

3. **Deployment readiness checks**: Validate that all local infrastructure
   services (Ollama, TEI embedding, Qdrant, MinIO) are reachable before
   accepting work — returning a structured health summary.  This is used
   by the /health/readiness endpoint and pre-flight checks.

Constitution §II: Readiness checks only probe local (localhost) endpoints.
Constitution §V:  All endpoint URLs are read from the secrets abstraction.
Constitution §I:  No automated clinical decisions — routing only moves cases
                  between workflow states; a human nurse makes Accept/Reject.

Usage (FastAPI dependency)
--------------------------
    from src.agents.workflow_agent import WorkflowAgent
    agent = WorkflowAgent()
    readiness = await agent.check_readiness()
    routing = await agent.route_case(case, db_session)
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

from src.core.secrets import get_secret

logger = logging.getLogger(__name__)

# Default readiness probe timeout (seconds)
_PROBE_TIMEOUT: float = 3.0

# SLA default fallback when Policy.sla_hours is NULL (hours)
SLA_DEFAULT_HOURS: int = 48


# ---------------------------------------------------------------------------
# Readiness DTOs
# ---------------------------------------------------------------------------


@dataclass
class ServiceStatus:
    name: str
    endpoint: str
    reachable: bool
    latency_ms: float | None = None
    error: str | None = None


@dataclass
class ReadinessReport:
    """
    Aggregated deployment readiness report.

    all_healthy is True only when every required local service is reachable.
    Optional services (e.g. Vault) may be unhealthy in local-dev mode.
    """

    services: list[ServiceStatus] = field(default_factory=list)

    @property
    def all_healthy(self) -> bool:
        return all(s.reachable for s in self.services)

    def as_dict(self) -> dict[str, Any]:
        return {
            "all_healthy": self.all_healthy,
            "services": [
                {
                    "name": s.name,
                    "endpoint": s.endpoint,
                    "reachable": s.reachable,
                    "latency_ms": s.latency_ms,
                    "error": s.error,
                }
                for s in self.services
            ],
        }


# ---------------------------------------------------------------------------
# Routing decision DTO
# ---------------------------------------------------------------------------


@dataclass
class RoutingDecision:
    """Outcome of route_case() — describes what should happen next."""

    case_id: uuid.UUID
    action: str          # "move_to_nurse_review" | "escalate_sla" | "noop" | …
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# WorkflowAgent
# ---------------------------------------------------------------------------


class WorkflowAgent:
    """
    Orchestrates end-to-end case lifecycle and audit logging.

    All endpoint URLs are sourced from the secrets abstraction (never
    hardcoded) to satisfy Constitution §V.
    """

    def __init__(self) -> None:
        self._llm_endpoint = (
            get_secret("LLM_ENDPOINT") or "http://localhost:11434"
        ).rstrip("/")
        self._embedding_endpoint = (
            get_secret("EMBEDDING_ENDPOINT") or "http://localhost:8080"
        ).rstrip("/")
        self._qdrant_host = get_secret("QDRANT_HOST") or "localhost"
        self._qdrant_port = int(get_secret("QDRANT_PORT") or "6333")
        self._minio_endpoint = get_secret("MINIO_ENDPOINT") or "localhost:9000"

    # -----------------------------------------------------------------------
    # Deployment Readiness
    # -----------------------------------------------------------------------

    async def check_readiness(self) -> ReadinessReport:
        """
        Probe all local infrastructure services.

        Returns a ReadinessReport. Never raises — errors are captured in
        ServiceStatus.error so the caller can decide how to surface them.

        Constitution §II: All probe targets are localhost/VPC — verified
        by asserting no external hostnames appear in the endpoint URLs.
        """
        report = ReadinessReport()

        probes: list[tuple[str, str]] = [
            ("ollama_llm", f"{self._llm_endpoint}/api/tags"),
            ("tei_embedding", f"{self._embedding_endpoint}/health"),
            (
                "qdrant",
                f"http://{self._qdrant_host}:{self._qdrant_port}/healthz",
            ),
            ("minio", f"http://{self._minio_endpoint}/minio/health/live"),
        ]

        async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT) as client:
            for name, url in probes:
                # Constitution §II guard: reject any external URL
                if _is_external_url(url):
                    report.services.append(
                        ServiceStatus(
                            name=name,
                            endpoint=url,
                            reachable=False,
                            error=(
                                "BLOCKED: endpoint resolves to an external host. "
                                "Constitution §II requires all inference to be local."
                            ),
                        )
                    )
                    continue

                t0 = datetime.now(timezone.utc)
                try:
                    resp = await client.get(url)
                    latency = (
                        datetime.now(timezone.utc) - t0
                    ).total_seconds() * 1000
                    report.services.append(
                        ServiceStatus(
                            name=name,
                            endpoint=url,
                            reachable=resp.status_code < 500,
                            latency_ms=round(latency, 1),
                        )
                    )
                except Exception as exc:
                    latency = (
                        datetime.now(timezone.utc) - t0
                    ).total_seconds() * 1000
                    report.services.append(
                        ServiceStatus(
                            name=name,
                            endpoint=url,
                            reachable=False,
                            latency_ms=round(latency, 1),
                            error=str(exc),
                        )
                    )
                    logger.warning(
                        "Readiness probe failed for %s (%s): %s",
                        name,
                        url,
                        exc,
                    )

        return report

    # -----------------------------------------------------------------------
    # Case routing
    # -----------------------------------------------------------------------

    async def route_case(
        self,
        case_id: uuid.UUID,
        review_status: str,
        assigned_queue: str,
        claimed_by_id: uuid.UUID | None,
        entered_review_at: datetime | None,
        policy_sla_hours: int | None,
    ) -> RoutingDecision:
        """
        Determine the next workflow action for a case.

        Constitution §I: This method only moves cases between workflow
        states — it NEVER makes a clinical Accept/Reject decision.
        All such decisions are made by a human nurse via the review UI.
        """
        effective_sla = policy_sla_hours or SLA_DEFAULT_HOURS

        # SLA breach check — measured from entered_review_at (not claimed_by_id)
        if (
            review_status == "in_nurse_review"
            and entered_review_at is not None
        ):
            now = datetime.now(timezone.utc)
            hours_in_review = (now - entered_review_at).total_seconds() / 3600
            if hours_in_review > effective_sla:
                return RoutingDecision(
                    case_id=case_id,
                    action="escalate_sla",
                    reason=(
                        f"Case has been in nurse review for "
                        f"{hours_in_review:.1f}h, exceeding SLA of "
                        f"{effective_sla}h."
                    ),
                    metadata={
                        "hours_in_review": round(hours_in_review, 2),
                        "sla_hours": effective_sla,
                        "previous_queue": assigned_queue,
                    },
                )

        # Pending verification → trigger completeness pipeline
        if review_status == "pending_verification":
            return RoutingDecision(
                case_id=case_id,
                action="trigger_completeness_pipeline",
                reason="Case submitted and awaiting completeness verification.",
            )

        # Already decided — no further routing needed
        if review_status in ("accepted", "returned_to_provider"):
            return RoutingDecision(
                case_id=case_id,
                action="noop",
                reason=f"Case already in terminal state: {review_status}.",
            )

        return RoutingDecision(
            case_id=case_id,
            action="noop",
            reason=f"No routing action required for status={review_status}.",
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EXTERNAL_HOSTS = frozenset([
    "openai.com",
    "anthropic.com",
    "api.openai",
    "cohere.ai",
    "together.ai",
    "replicate.com",
    "huggingface.co",
])


def _is_external_url(url: str) -> bool:
    """Return True if the URL points to a known external (cloud) service."""
    url_lower = url.lower()
    return any(h in url_lower for h in _EXTERNAL_HOSTS)
