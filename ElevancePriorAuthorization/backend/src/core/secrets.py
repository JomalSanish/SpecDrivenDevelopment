"""
backend/src/core/secrets.py

Secrets-manager abstraction for the PA Evidence Assistant.

Constitution Principle V mandates: ALL credentials go through this layer
from Phase 1. No code elsewhere may call os.environ directly for secrets.

Supported backends (configured via SECRETS_BACKEND env var):
  "vault"  — HashiCorp Vault KV v2 (production / staging)
  "env"    — pydantic-settings / .env.local (local dev only)

Usage
-----
    from src.core.secrets import get_secret, SecretsManager

    # Simple key lookup (falls through to the configured backend)
    db_url = get_secret("DATABASE_URL")

    # Or inject the manager directly (useful for testing with a mock)
    manager = SecretsManager()
    value = manager.get("MINIO_ACCESS_KEY")
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class BaseSecretsBackend(ABC):
    """All secrets backends must implement this interface."""

    @abstractmethod
    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Retrieve *key* from the secrets store, returning *default* if absent."""

    def require(self, key: str) -> str:
        """Like get(), but raises ValueError if the key is missing."""
        value = self.get(key)
        if value is None:
            raise ValueError(
                f"Required secret '{key}' is not available in the "
                f"{self.__class__.__name__} backend."
            )
        return value


# ---------------------------------------------------------------------------
# Backend: Env / pydantic-settings (local dev only)
# ---------------------------------------------------------------------------

class EnvSecretsBackend(BaseSecretsBackend):
    """
    Reads secrets from the process environment / .env.local via the
    pydantic Settings object.  Intended for local development ONLY.
    Never used in production or staging environments.
    """

    def __init__(self) -> None:
        # Import lazily to avoid circular imports
        from src.core.config import settings as _settings
        self._settings = _settings
        logger.warning(
            "SecretsManager is using the ENV backend. "
            "This is acceptable for local development only. "
            "Set SECRETS_BACKEND=vault in production."
        )

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        # pydantic-settings exposes settings as attributes; fall back to
        # the raw environment so arbitrary keys also work.
        value = getattr(self._settings, key, None)
        if value is not None:
            return str(value)
        return os.environ.get(key, default)


# ---------------------------------------------------------------------------
# Backend: HashiCorp Vault KV v2
# ---------------------------------------------------------------------------

class VaultSecretsBackend(BaseSecretsBackend):
    """
    Reads secrets from HashiCorp Vault KV v2.
    Requires the 'hvac' library (included in requirements.txt).

    All secrets for this application are expected under the path:
        {VAULT_MOUNT}/data/{VAULT_PATH}

    The full secret payload is loaded once and cached.  Call
    `invalidate_cache()` to force a refresh (e.g. on rotation).
    """

    def __init__(
        self,
        vault_addr: Optional[str] = None,
        vault_token: Optional[str] = None,
        vault_mount: Optional[str] = None,
        vault_path: Optional[str] = None,
    ) -> None:
        try:
            import hvac  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "hvac is required for the Vault backend. "
                "Install it with: pip install hvac"
            ) from exc

        from src.core.config import settings

        self._client = hvac.Client(
            url=vault_addr or settings.VAULT_ADDR,
            token=vault_token or settings.VAULT_TOKEN,
        )
        self._mount = vault_mount or settings.VAULT_MOUNT
        self._path = vault_path or settings.VAULT_PATH
        self._cache: Optional[dict[str, str]] = None

        if not self._client.is_authenticated():
            raise RuntimeError(
                f"Vault client at {self._client.url} is not authenticated. "
                "Check VAULT_TOKEN or configure AppRole / Kubernetes auth."
            )

        logger.info(
            "VaultSecretsBackend initialized: addr=%s mount=%s path=%s",
            self._client.url,
            self._mount,
            self._path,
        )

    def _load(self) -> dict[str, str]:
        if self._cache is None:
            response = self._client.secrets.kv.v2.read_secret_version(
                mount_point=self._mount,
                path=self._path,
                raise_on_deleted_version=True,
            )
            self._cache = response["data"]["data"]
            logger.debug("Loaded %d secrets from Vault path '%s'.", len(self._cache), self._path)
        return self._cache

    def invalidate_cache(self) -> None:
        """Force the next get() call to re-fetch from Vault (e.g. after rotation)."""
        self._cache = None

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        try:
            payload = self._load()
        except Exception as exc:
            logger.error("Failed to read secrets from Vault: %s", exc)
            return default
        return payload.get(key, default)


# ---------------------------------------------------------------------------
# SecretsManager facade
# ---------------------------------------------------------------------------

class SecretsManager:
    """
    Public facade for the secrets layer.

    Selects the appropriate backend based on the SECRETS_BACKEND
    environment variable (not a secrets value itself — bootstrapping).

    Instantiation is cheap; the backend is lazy-initialised.
    """

    def __init__(self) -> None:
        backend_name = os.environ.get("SECRETS_BACKEND", "env").lower()
        self._backend: BaseSecretsBackend = self._create_backend(backend_name)

    @staticmethod
    def _create_backend(name: str) -> BaseSecretsBackend:
        if name == "vault":
            return VaultSecretsBackend()
        if name == "env":
            return EnvSecretsBackend()
        raise ValueError(
            f"Unknown SECRETS_BACKEND '{name}'. Supported values: 'vault', 'env'."
        )

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        return self._backend.get(key, default)

    def require(self, key: str) -> str:
        return self._backend.require(key)


# ---------------------------------------------------------------------------
# Module-level convenience accessor (singleton, cached)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _get_manager() -> SecretsManager:
    """Return the process-level SecretsManager singleton."""
    return SecretsManager()


def get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    """
    Convenience function to retrieve a secret by key.

    >>> db_url = get_secret("DATABASE_URL")
    """
    return _get_manager().get(key, default)


def require_secret(key: str) -> str:
    """
    Like get_secret() but raises ValueError if the key is absent.

    >>> db_url = require_secret("DATABASE_URL")
    """
    return _get_manager().require(key)
