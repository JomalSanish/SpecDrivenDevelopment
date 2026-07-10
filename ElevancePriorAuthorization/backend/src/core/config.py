"""
backend/src/core/config.py
Application settings loaded via pydantic-settings.
All connection strings are fetched through the secrets abstraction
(src/core/secrets.py) — never read directly from env here in production.
In local dev the .env.local file is used for convenience only.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Secrets backend — "vault" | "env" (local dev only)
    SECRETS_BACKEND: str = "env"

    # HashiCorp Vault (used when SECRETS_BACKEND=vault)
    VAULT_ADDR: str = "http://127.0.0.1:8200"
    VAULT_TOKEN: str = ""
    VAULT_MOUNT: str = "secret"
    VAULT_PATH: str = "pa-evidence-assistant"

    # PostgreSQL (populated by secrets manager at startup)
    DATABASE_URL: str = "postgresql+asyncpg://pa_user:pa_password@localhost:5432/pa_evidence"

    # MinIO (populated by secrets manager at startup)
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "pa-case-documents"
    MINIO_SECURE: bool = False

    # Qdrant
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333

    # Local embedding endpoint (TEI / SentenceTransformers)
    EMBEDDING_ENDPOINT: str = "http://localhost:8080"

    # Local LLM endpoint (Ollama / vLLM)
    LLM_ENDPOINT: str = "http://localhost:11434"
    LLM_MODEL: str = "llama3"

    model_config = SettingsConfigDict(
        env_file=".env.local",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
