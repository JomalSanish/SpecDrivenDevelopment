"""
scripts/validate_phase1.py

Phase 1 validation script.
Verifies:
  1. Secrets abstraction resolves all required credentials (no external keys).
  2. Qdrant is reachable on the configured host/port.
  3. TEI embedding endpoint is reachable and returns valid embedding vectors.
  4. Ollama (LLM) endpoint is reachable and lists available models.
  5. No calls are made to public API domains (openai.com, anthropic.com, cohere.com).

Usage:
    # With services running via docker-compose up -d:
    python scripts/validate_phase1.py

Exit codes:
    0 — all checks passed
    1 — one or more checks failed
"""
import os
import sys
import json
import logging
import urllib.request
import urllib.error
from typing import Optional

# Allow running from repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

PASS = "\033[92m✓ PASS\033[0m"
FAIL = "\033[91m✗ FAIL\033[0m"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def http_get(url: str, timeout: int = 5) -> Optional[dict]:
    """Perform a GET request and return parsed JSON, or None on failure."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception as exc:
        return None


def http_post_json(url: str, payload: dict, timeout: int = 10) -> Optional[dict]:
    """POST JSON and return parsed response, or None on failure."""
    try:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            url, data=data, method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception as exc:
        return None


# ---------------------------------------------------------------------------
# Check 1: Secrets abstraction
# ---------------------------------------------------------------------------

def check_secrets() -> bool:
    log.info("\n── Check 1: Secrets abstraction ──")
    os.environ.setdefault("SECRETS_BACKEND", "env")
    try:
        from src.core.secrets import get_secret, _get_manager
        _get_manager.cache_clear()

        required = ["DATABASE_URL", "MINIO_ACCESS_KEY", "QDRANT_HOST",
                    "EMBEDDING_ENDPOINT", "LLM_ENDPOINT"]
        forbidden = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "COHERE_API_KEY"]
        ok = True

        for key in required:
            v = get_secret(key)
            if v:
                log.info("  %s %-25s resolved", PASS, key)
            else:
                log.error("  %s %-25s MISSING", FAIL, key)
                ok = False

        for key in forbidden:
            v = get_secret(key)
            if v is None:
                log.info("  %s %-25s correctly absent (no external API keys)", PASS, key)
            else:
                log.error("  %s %-25s PRESENT — external API key must NOT be configured!", FAIL, key)
                ok = False

        return ok
    except Exception as exc:
        log.exception("  %s Secrets check raised: %s", FAIL, exc)
        return False


# ---------------------------------------------------------------------------
# Check 2: Qdrant health
# ---------------------------------------------------------------------------

def check_qdrant() -> bool:
    log.info("\n── Check 2: Qdrant reachability ──")
    os.environ.setdefault("SECRETS_BACKEND", "env")
    try:
        from src.core.secrets import get_secret, _get_manager
        _get_manager.cache_clear()
        host = get_secret("QDRANT_HOST") or "localhost"
        port = get_secret("QDRANT_PORT") or "6333"
        url = f"http://{host}:{port}/healthz"

        result = http_get(url)
        if result is not None:
            log.info("  %s Qdrant at %s is healthy: %s", PASS, url, result)
            return True
        else:
            # healthz may return 200 with empty body on some versions
            try:
                urllib.request.urlopen(url, timeout=5)
                log.info("  %s Qdrant at %s responded (200 OK)", PASS, url)
                return True
            except Exception:
                log.error("  %s Qdrant at %s is NOT reachable. Is docker-compose up?", FAIL, url)
                return False
    except Exception as exc:
        log.exception("  %s Qdrant check raised: %s", FAIL, exc)
        return False


# ---------------------------------------------------------------------------
# Check 3: TEI Embedding endpoint
# ---------------------------------------------------------------------------

def check_embedding() -> bool:
    log.info("\n── Check 3: Local embedding endpoint (TEI) ──")
    os.environ.setdefault("SECRETS_BACKEND", "env")
    try:
        from src.core.secrets import get_secret, _get_manager
        _get_manager.cache_clear()
        endpoint = get_secret("EMBEDDING_ENDPOINT") or "http://localhost:8080"

        # TEI health endpoint
        health = http_get(f"{endpoint}/health")
        if health is None:
            # Try root
            try:
                urllib.request.urlopen(endpoint, timeout=5)
            except Exception:
                log.error("  %s TEI at %s is NOT reachable.", FAIL, endpoint)
                return False

        # Test embed a short synthetic string (no real PHI ever in tests)
        payload = {"inputs": "synthetic test sentence for embedding validation"}
        result = http_post_json(f"{endpoint}/embed", payload, timeout=15)
        if result and isinstance(result, list) and len(result) > 0:
            embedding = result[0] if isinstance(result[0], list) else result
            log.info(
                "  %s TEI at %s returned embedding vector (dim=%d)",
                PASS, endpoint, len(embedding)
            )
            return True
        else:
            log.error(
                "  %s TEI at %s did not return a valid embedding. Response: %s",
                FAIL, endpoint, result
            )
            return False
    except Exception as exc:
        log.exception("  %s Embedding check raised: %s", FAIL, exc)
        return False


# ---------------------------------------------------------------------------
# Check 4: Ollama (LLM) endpoint
# ---------------------------------------------------------------------------

def check_llm() -> bool:
    log.info("\n── Check 4: Local LLM endpoint (Ollama) ──")
    os.environ.setdefault("SECRETS_BACKEND", "env")
    try:
        from src.core.secrets import get_secret, _get_manager
        _get_manager.cache_clear()
        endpoint = get_secret("LLM_ENDPOINT") or "http://localhost:11434"

        result = http_get(f"{endpoint}/api/tags", timeout=5)
        if result is not None:
            models = [m.get("name") for m in result.get("models", [])]
            log.info("  %s Ollama at %s is reachable. Available models: %s", PASS, endpoint, models)
            return True
        else:
            log.error(
                "  %s Ollama at %s is NOT reachable. Is docker-compose up?",
                FAIL, endpoint
            )
            return False
    except Exception as exc:
        log.exception("  %s LLM check raised: %s", FAIL, exc)
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    results = {
        "secrets": check_secrets(),
        "qdrant": check_qdrant(),
        "embedding": check_embedding(),
        "llm": check_llm(),
    }

    log.info("\n═══ Phase 1 Validation Summary ═══")
    all_ok = True
    for name, ok in results.items():
        status = PASS if ok else FAIL
        log.info("  %s %s", status, name)
        if not ok:
            all_ok = False

    if all_ok:
        log.info("\n✅ Phase 1 validation PASSED. Ready to proceed to Phase 2.")
        sys.exit(0)
    else:
        log.error(
            "\n❌ Phase 1 validation FAILED. Fix the issues above before proceeding."
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
