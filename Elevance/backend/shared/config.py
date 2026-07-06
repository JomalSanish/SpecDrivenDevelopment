import os
from typing import Protocol, Any

class SecretsProvider(Protocol):
    def get_secret(self, key: str, default: Any = "") -> str:
        ...

class EnvSecretsProvider:
    """Reads secrets from local environment variables."""
    def get_secret(self, key: str, default: Any = "") -> str:
        return os.environ.get(key, default)

# Swap this with AwsSecretsProvider or VaultSecretsProvider in production
_provider = EnvSecretsProvider()

class Config:
    @property
    def SYNTHETIC_DATA_ONLY(self) -> bool:
        return _provider.get_secret("SYNTHETIC_DATA_ONLY", "true").lower() == "true"
    
    @property
    def ANTHROPIC_API_KEY(self) -> str:
        return _provider.get_secret("ANTHROPIC_API_KEY", "")
    
    @property
    def DATABASE_URL(self) -> str:
        return _provider.get_secret("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")

settings = Config()
