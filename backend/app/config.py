from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    database_url: str | None = None
    api_cors_origins: str = 'http://localhost:3000,http://127.0.0.1:3000'
    openai_embedding_api_key: str | None = None
    openai_chat_api_key: str | None = None
    openai_api_key: str | None = None
    openai_chat_model: str = 'gpt-6-luna'
    openai_embedding_model: str = 'text-embedding-3-small'
    embedding_provider: str = 'openai'
    azure_openai_endpoint: str | None = None
    azure_openai_api_key: str | None = None
    azure_openai_embedding_deployment: str | None = None
    azure_openai_api_version: str | None = None
    max_request_bytes: int = 32768

    model_config = SettingsConfigDict(env_file=ROOT / '.env', extra='ignore', case_sensitive=False)

    @property
    def cors_origins(self) -> list[str]:
        return [item.strip() for item in self.api_cors_origins.split(',') if item.strip()]

    @property
    def resolved_openai_embedding_api_key(self) -> str | None:
        return self.openai_embedding_api_key or self.openai_api_key or None

    @property
    def resolved_openai_chat_api_key(self) -> str | None:
        return self.openai_chat_api_key or self.openai_api_key or None


@lru_cache
def get_settings() -> Settings:
    return Settings()
