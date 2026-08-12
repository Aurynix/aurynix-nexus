# Background Workers

Heavy tasks that would block an HTTP response run in an ARQ worker process. ARQ (Async Redis Queue) uses Redis as the job broker — no additional infrastructure beyond the existing Redis service.

---

## Why Background Workers?

| Task | Without workers | With workers |
|---|---|---|
| PDF upload (50 pages, 1000 chunks) | Request hangs for 30 s+ | Returns `202` immediately; document status updates async |
| Large batch embed | Timeout | Runs in background; trackable via job ID |

---

## Architecture

```
POST /api/v1/documents/upload
        │
        ▼
arq create_pool → enqueue_job("ingest_document", doc_id=..., ...)
Returns 202 { "status": "processing", "job_id": "abc123" }
        │
Redis (job queue)
        │
        ▼
ARQ Worker (separate process — app/workers/settings.py)
        │
        ├── pull job from Redis
        ├── run ingest_document() — embed chunks, upsert to Qdrant
        ├── UPDATE documents SET status='ready', chunk_count=N
        └── on failure: UPDATE documents SET status='failed', error_message='...'
```

**Fallback:** If Redis is unavailable when the upload request arrives, the service falls back to `asyncio.create_task` (in-process). The upload still returns `202` but no `job_id` is returned.

---

## Implemented Job

### `ingest_document` (`app/workers/tasks.py`)

```python
async def ingest_document(
    ctx: dict,
    *,
    file_path: str,
    doc_id: str,
    user_id: str,
    db_url: str,
) -> dict:
    pipeline = RAGPipeline()
    chunk_count = await pipeline.ingest(Path(file_path), doc_id=doc_id, user_id=user_id)
    # Updates Document.status in Postgres, returns {"doc_id", "status", "chunk_count"}
```

The task opens its own DB connection (`db_url` passed as argument) so it runs independently of the web process.

---

## Worker Configuration (`app/workers/settings.py`)

```python
class WorkerSettings:
    functions = [ingest_document]
    on_startup = startup        # calls configure_logging()
    max_jobs = 10               # concurrent jobs per worker process
    job_timeout = 300           # 5 minutes max per job

    @property
    def redis_settings(self):
        return ArqRedisSettings(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password or None,
        )
```

**Run the worker:**
```bash
uv run python -m arq app.workers.settings.WorkerSettings
```

---

## Docker Compose

The worker runs as a separate service:

```yaml
worker:
  build:
    context: .
    dockerfile: docker/Dockerfile
  command: python -m arq app.workers.settings.WorkerSettings
  env_file: .env
  environment:
    POSTGRES_HOST: postgres
    REDIS_HOST: redis
    QDRANT_HOST: qdrant
  volumes:
    - uploads_data:/app/uploads
  depends_on:
    postgres:
      condition: service_healthy
    redis:
      condition: service_healthy
    qdrant:
      condition: service_healthy
  restart: unless-stopped
```

Scale for higher throughput:
```bash
docker compose up --scale worker=4
```

---

## Job Status API

```
GET /api/v1/documents/jobs/{job_id}
```

Requires JWT auth. Returns the current ARQ job status.

```json
{
  "job_id": "abc123",
  "status": "complete",
  "result": { "doc_id": "...", "status": "ready", "chunk_count": 47 }
}
```

Possible `status` values: `queued`, `in_progress`, `complete`, `not_found`, `error`.

Document upload returns `job_id` directly in the response body:

```json
{
  "id": "550e8400-...",
  "filename": "report.pdf",
  "status": "processing",
  "job_id": "abc123",
  ...
}
```
