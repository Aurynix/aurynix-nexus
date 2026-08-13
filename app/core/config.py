import json
from functools import lru_cache
from typing import Literal
from urllib.parse import quote

from pydantic import AliasChoices, Field, field_validator
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

    # PostgreSQL — either set DATABASE_URL (cloud) or individual fields (local)
    database_url: str = ""
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "aurynix"
    postgres_user: str = "aurynix"
    postgres_password: str = "changeme"

    # Redis — either set REDIS_URL (cloud) or individual fields (local)
    redis_url_override: str = Field(
        default="", validation_alias=AliasChoices("REDIS_URL", "redis_url_override")
    )
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""
    redis_ssl: bool = False

    # Qdrant — either set QDRANT_URL (cloud) or individual fields (local)
    qdrant_url: str = ""
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "aurynix_docs"
    qdrant_api_key: str = ""
    qdrant_use_https: bool = False

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

    # Phase 2 — Observability
    otlp_endpoint: str = ""
    sentry_dsn: str = ""
    sentry_traces_sample_rate: float = 0.1

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

    def _pg_base(self, driver: str) -> str:
        if self.database_url:
            raw = self.database_url
            raw = raw.replace("postgresql://", f"postgresql+{driver}://", 1)
            raw = raw.replace("postgres://", f"postgresql+{driver}://", 1)
            if driver == "asyncpg":
                # asyncpg doesn't accept URL query params; SSL passed via connect_args
                raw = raw.split("?")[0]
            return raw
        return f"postgresql+{driver}://{self._pg_userinfo}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

    @property
    def async_database_url(self) -> str:
        return self._pg_base("asyncpg")

    @property
    def sync_database_url(self) -> str:
        return self._pg_base("psycopg2")

    @property
    def checkpointer_database_url(self) -> str:
        if self.database_url:
            raw = self.database_url
            raw = raw.replace("postgresql+asyncpg://", "postgresql://", 1)
            raw = raw.replace("postgresql+psycopg2://", "postgresql://", 1)
            return raw
        return f"postgresql://{self._pg_userinfo}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

    @property
    def redis_url(self) -> str:
        if self.redis_url_override:
            return self.redis_url_override
        scheme = "rediss" if self.redis_ssl else "redis"
        if self.redis_password:
            return f"{scheme}://:{self.redis_password}@{self.redis_host}:{self.redis_port}/0"
        return f"{scheme}://{self.redis_host}:{self.redis_port}/0"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
