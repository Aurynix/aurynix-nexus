import json
from functools import lru_cache
from typing import Literal
from urllib.parse import quote

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Groq (LLM)
    groq_api_key: str = ""
    model_name: str = "llama-3.3-70b-versatile"

    # Embeddings — FastEmbed (local, no API key)
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dimensions: int = 384

    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "aurynix"
    postgres_user: str = "aurynix"
    postgres_password: str = "changeme"

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""

    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "aurynix_docs"

    # Auth
    secret_key: str = "change-me"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 30
    algorithm: str = "HS256"

    # App
    environment: Literal["development", "staging", "production"] = "development"
    log_level: str = "INFO"
    cors_origins: list[str] = ["http://localhost:3000"]

    # File storage
    upload_dir: str = "./uploads"
    max_upload_size_mb: int = 50

    # Phase 2 — web search
    tavily_api_key: str = ""

    # Phase 2 — rate limiting
    rate_limit_chat: int = 20
    rate_limit_auth: int = 10
    rate_limit_documents: int = 30
    rate_limit_default: int = 60

    # Phase 2 — Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/v1/oauth/google/callback"
    oauth_success_redirect: str = "http://localhost:3000/settings?oauth=success"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | list) -> list[str]:
        if isinstance(v, str):
            return json.loads(v)
        return v

    # ── Computed URLs ──────────────────────────────────────────────────────

    @property
    def _pg_userinfo(self) -> str:
        return f"{quote(self.postgres_user, safe='')}:{quote(self.postgres_password, safe='')}"

    @property
    def async_database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self._pg_userinfo}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def sync_database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self._pg_userinfo}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def checkpointer_database_url(self) -> str:
        return (
            f"postgresql://{self._pg_userinfo}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/0"
        return f"redis://{self.redis_host}:{self.redis_port}/0"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
