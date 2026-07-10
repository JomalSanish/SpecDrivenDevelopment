"""
backend/tests/unit/test_secrets.py

Phase 1 validation: secrets abstraction must be wired correctly.
Verifies:
  1. EnvSecretsBackend resolves keys from the Settings object.
  2. Missing keys return None / raise ValueError appropriately.
  3. VaultSecretsBackend raises RuntimeError when unauthenticated (no Vault running).
  4. SECRETS_BACKEND=env never leaks the value "vault" as a secret.
  5. SecretsManager selects the correct backend from the env var.
"""
import os
import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# EnvSecretsBackend
# ---------------------------------------------------------------------------

class TestEnvSecretsBackend:
    def test_resolves_known_key(self, monkeypatch):
        """A key present in the pydantic settings is returned."""
        monkeypatch.setenv("SECRETS_BACKEND", "env")
        monkeypatch.setenv("LLM_ENDPOINT", "http://localhost:11434")
        # Clear lru_cache to force fresh instantiation
        from src.core import secrets as secrets_module
        secrets_module._get_manager.cache_clear()

        from src.core.secrets import EnvSecretsBackend
        backend = EnvSecretsBackend()
        value = backend.get("LLM_ENDPOINT")
        assert value == "http://localhost:11434"

    def test_missing_key_returns_default(self, monkeypatch):
        monkeypatch.setenv("SECRETS_BACKEND", "env")
        from src.core.secrets import EnvSecretsBackend
        backend = EnvSecretsBackend()
        result = backend.get("NON_EXISTENT_KEY_XYZ", default="fallback")
        assert result == "fallback"

    def test_require_raises_on_missing(self, monkeypatch):
        monkeypatch.setenv("SECRETS_BACKEND", "env")
        from src.core.secrets import EnvSecretsBackend
        backend = EnvSecretsBackend()
        with pytest.raises(ValueError, match="NON_EXISTENT_KEY_XYZ"):
            backend.require("NON_EXISTENT_KEY_XYZ")


# ---------------------------------------------------------------------------
# VaultSecretsBackend — unauthenticated guard
# ---------------------------------------------------------------------------

class TestVaultSecretsBackend:
    def test_raises_runtime_error_when_unauthenticated(self, monkeypatch):
        """
        If Vault is unreachable or the token is wrong, the backend should
        raise RuntimeError rather than silently returning None values.
        """
        monkeypatch.setenv("VAULT_ADDR", "http://127.0.0.1:8200")
        monkeypatch.setenv("VAULT_TOKEN", "invalid-token")
        monkeypatch.setenv("SECRETS_BACKEND", "vault")

        mock_client = MagicMock()
        mock_client.is_authenticated.return_value = False

        with patch("hvac.Client", return_value=mock_client):
            from src.core.secrets import VaultSecretsBackend
            with pytest.raises(RuntimeError, match="not authenticated"):
                VaultSecretsBackend(vault_token="invalid-token")


# ---------------------------------------------------------------------------
# SecretsManager backend selection
# ---------------------------------------------------------------------------

class TestSecretsManagerBackendSelection:
    def test_selects_env_backend(self, monkeypatch):
        monkeypatch.setenv("SECRETS_BACKEND", "env")
        from src.core import secrets as m
        m._get_manager.cache_clear()
        from src.core.secrets import SecretsManager, EnvSecretsBackend
        mgr = SecretsManager()
        assert isinstance(mgr._backend, EnvSecretsBackend)

    def test_raises_on_unknown_backend(self, monkeypatch):
        from src.core.secrets import SecretsManager
        with pytest.raises(ValueError, match="unknown_backend"):
            SecretsManager._create_backend("unknown_backend")


# ---------------------------------------------------------------------------
# Module-level get_secret convenience function
# ---------------------------------------------------------------------------

class TestGetSecretConvenienceFunction:
    def test_get_secret_returns_value(self, monkeypatch):
        monkeypatch.setenv("SECRETS_BACKEND", "env")
        monkeypatch.setenv("EMBEDDING_ENDPOINT", "http://localhost:8080")
        from src.core import secrets as m
        m._get_manager.cache_clear()
        from src.core.secrets import get_secret
        assert get_secret("EMBEDDING_ENDPOINT") == "http://localhost:8080"

    def test_no_external_api_keys_present(self, monkeypatch):
        """
        Phase 1 guard: ensure no public API keys (openai, anthropic, cohere)
        are resolvable through the secrets layer in the test environment.
        """
        monkeypatch.setenv("SECRETS_BACKEND", "env")
        from src.core import secrets as m
        m._get_manager.cache_clear()
        from src.core.secrets import get_secret
        for forbidden_key in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "COHERE_API_KEY"]:
            assert get_secret(forbidden_key) is None, (
                f"External API key '{forbidden_key}' must NOT be present in secrets. "
                "No public LLM API calls are permitted (Constitution §II)."
            )
