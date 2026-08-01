# Configuration

All configuration is read from a `.env` file in the project root. Copy `.env.example` as a starting point:

```bash
cp .env.example .env
```

---

## LLM

| Variable | Default | Description |
|---|---|---|
| `GROQ_API_KEY` | *(required)* | Groq API key — get from [console.groq.com](https://console.groq.com) |
| `MODEL_NAME` | `llama-3.3-70b-versatile` | Groq model to use for the agent |

---

## Embeddings

FastEmbed runs locally — no API key needed.

| Variable | Default | Description |
|---|---|---|
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | FastEmbed model name |
| `EMBEDDING_DIMENSIONS` | `384` | Vector dimensions — must match the model |

Available models: https://qdrant.github.io/fastembed/examples/Supported_Models/

> **Important:** If you change `EMBEDDING_MODEL`, you must also update `EMBEDDING_DIMENSIONS` to match, then recreate the Qdrant collection (`docker compose down -v && make seed-db`).

---

## PostgreSQL

| Variable | Default | Description |
|---|---|---|
| `POSTGRES_HOST` | `localhost` | Database host |
| `POSTGRES_PORT` | `5432` | Database port |
| `POSTGRES_DB` | `aurynix` | Database name |
| `POSTGRES_USER` | `aurynix` | Database user |
| `POSTGRES_PASSWORD` | `changeme` | Database password — special characters (`@`, `/`) are safe |

---

## Redis

| Variable | Default | Description |
|---|---|---|
| `REDIS_HOST` | `localhost` | Redis host |
| `REDIS_PORT` | `6379` | Redis port |
| `REDIS_PASSWORD` | *(empty)* | Redis password — leave empty for no auth |

---

## Qdrant

| Variable | Default | Description |
|---|---|---|
| `QDRANT_HOST` | `localhost` | Qdrant host |
| `QDRANT_PORT` | `6333` | Qdrant HTTP port |
| `QDRANT_COLLECTION` | `aurynix_docs` | Collection name for document vectors |

---

## Auth

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | *(required)* | JWT signing secret — generate with `openssl rand -hex 32` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | Access token lifetime |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `30` | Refresh token lifetime |

> **Warning:** Never commit your real `SECRET_KEY` to git. Rotate it if it is ever exposed — all existing tokens will be invalidated.

---

## App

| Variable | Default | Description |
|---|---|---|
| `ENVIRONMENT` | `development` | `development`, `staging`, or `production` |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `CORS_ORIGINS` | `["http://localhost:3000","http://localhost:5173"]` | JSON array of allowed CORS origins |

In `production` mode the `/docs` and `/redoc` endpoints are disabled.

---

## File Storage

| Variable | Default | Description |
|---|---|---|
| `UPLOAD_DIR` | `./uploads` | Directory where uploaded files are saved before ingestion |
| `MAX_UPLOAD_SIZE_MB` | `50` | Maximum upload file size in megabytes |

---

## How settings are loaded

Settings are defined in `app/core/config.py` using Pydantic `BaseSettings`. The class reads from environment variables (case-insensitive) and falls back to `.env`. The singleton `settings` object is cached with `@lru_cache`.

Three computed URL properties are derived automatically:

```python
settings.async_database_url       # postgresql+asyncpg://... (SQLAlchemy)
settings.sync_database_url        # postgresql+psycopg2://... (Alembic only)
settings.checkpointer_database_url  # postgresql://... (LangGraph)
settings.redis_url                # redis://:pass@host:port/0
```

Passwords with special characters are percent-encoded using `urllib.parse.quote` so they are safe in all URL formats.
