"""
scripts/init_secrets.py

Bootstrap script that verifies the secrets abstraction is wired correctly
and populates Vault (if backend=vault) with initial dev defaults.

Usage (local dev):
    SECRETS_BACKEND=env python scripts/init_secrets.py

Usage (vault):
    VAULT_ADDR=http://127.0.0.1:8200 VAULT_TOKEN=root \\
    SECRETS_BACKEND=vault python scripts/init_secrets.py
"""
import os
import sys
import logging

# Allow running from repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

REQUIRED_SECRETS = [
    "DATABASE_URL",
    "MINIO_ACCESS_KEY",
    "MINIO_SECRET_KEY",
    "QDRANT_HOST",
    "EMBEDDING_ENDPOINT",
    "LLM_ENDPOINT",
]


def main() -> None:
    from src.core.secrets import get_secret

    backend = os.environ.get("SECRETS_BACKEND", "env")
    logger.info("Checking secrets via backend: %s", backend)

    all_ok = True
    for key in REQUIRED_SECRETS:
        value = get_secret(key)
        if value:
            logger.info("  ✓ %-25s = %s", key, value[:8] + "..." if len(value) > 8 else value)
        else:
            logger.error("  ✗ %-25s — MISSING", key)
            all_ok = False

    if all_ok:
        logger.info("\nAll required secrets resolved. Secrets abstraction is wired correctly.")
    else:
        logger.error("\nSome secrets are missing. Check your .env.local or Vault configuration.")
        sys.exit(1)


if __name__ == "__main__":
    main()
