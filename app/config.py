"""Runtime configuration (12-factor, via environment variables or `.env`)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_PLACEHOLDER_PREFIXES = ("your", "changeme", "<", "sk-xxx", "sk-ant-xxx", "replace")


def usable_secret(secret: SecretStr | None) -> str | None:
    """Return the secret value unless it is empty or an obvious placeholder from `.env.example`."""
    if secret is None:
        return None
    value = secret.get_secret_value().strip()
    if not value or value.lower().startswith(_PLACEHOLDER_PREFIXES) or "..." in value:
        return None
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    service_name: str = "tailor-ai-engine"
    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"

    # LLM — "auto" picks Anthropic, then OpenAI, then the deterministic rule-based planner.
    llm_provider: Literal["auto", "anthropic", "openai", "none"] = "auto"
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-opus-5-5"
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-4.1-mini"
    llm_timeout_seconds: float = 30.0
    llm_max_tool_rounds: int = 4
    # Global budget of LLM-backed requests per minute; beyond it requests run rule-based (no error).
    llm_max_requests_per_minute: int = Field(default=30, ge=0)

    # Catalog repository (the request payload always wins).
    catalog_path: Path | None = None
    catalog_database_url: str | None = None

    # HTTP — restrictive by default: list your storefront origin(s) in production.
    cors_allow_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = Field(default=120, ge=1)
    stylist_rate_limit_per_minute: int = Field(default=20, ge=1)
    max_request_bytes: int = Field(default=1_000_000, ge=1_024)

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
