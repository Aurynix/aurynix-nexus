# Background Workers

Heavy tasks that would block an HTTP response run in an ARQ worker pool. ARQ (Async Redis Queue) uses Redis as the job broker — no additional infrastructure is needed beyond the existing Redis service.

---

## Why Background Workers?

| Task | Without workers | With workers |
|---|---|---|
| PDF upload (50 pages) | Request hangs for 30s+ | Returns immediately; document status updates async |
| Batch embed 1000 chunks | Timeout | Runs in background; progress trackable |
| Send bulk notifications | Blocks request | Queued, retried on failure |
| Nightly memory consolidation | Manual cron | Scheduled ARQ job |

---

## Architecture

```
FastAPI handler
    │
    ▼
await arq_pool.enqueue_job("ingest_document", doc_id=..., user_id=...)
    │
    ▼
Redis (job queue)
    │
    ▼
ARQ Worker (separate process)
    │
    ├── pull job
    ├── execute async function
    ├── update Document.status in Postgres
    └── retry on failure (max 3 attempts, exponential backoff)
```

---

## Job Types

### `ingest_document`

Replaces the `asyncio.create_task()` pattern from Phase 1. The worker runs the full RAG ingest pipeline and updates the document status.

```python
# app/workers/jobs.py
async def ingest_document(ctx, *, doc_id: str, user_id: str, file_path: str) -> None:
    pipeline = RAGPipeline()
    try:
        chunk_count = await pipeline.ingest(Path(file_path), doc_id=doc_id, user_id=user_id)
        await set_document_status(doc_id, "ready", chunk_count=chunk_count)
    except Exception as exc:
        await set_document_status(doc_id, "failed", error=str(exc))
        raise  # ARQ will retry
```

### `send_handoff_notification`

Posts a handoff webhook and optionally sends a Slack message when the agent triggers a human handoff.

```python
async def send_handoff_notification(ctx, *, payload: dict) -> None:
    if settings.handoff_webhook_url:
        async with httpx.AsyncClient() as client:
            await client.post(settings.handoff_webhook_url, json=payload)
```

### `consolidate_memory`

Nightly job that reviews long conversation histories per user, extracts durable facts, and upserts them into the memory store. Scheduled via ARQ's cron mechanism.

```python
async def consolidate_memory(ctx) -> None:
    users = await list_active_users()
    for user_id in users:
        await extract_and_store_facts(user_id)
```

### `cleanup_expired_uploads`

Deletes files from disk for documents that failed ingestion more than 24 hours ago.

---

## Worker Configuration

```bash
# pyproject.toml [project.scripts]
# or run directly:
uv run arq app.workers.main.WorkerSettings
```

```python
# app/workers/main.py
class WorkerSettings:
    functions = [
        ingest_document,
        send_handoff_notification,
        consolidate_memory,
        cleanup_expired_uploads,
    ]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 10                    # concurrent jobs per worker process
    job_timeout = 300                # 5 minutes max per job
    keep_result = 3600               # keep result in Redis for 1 hour
    retry_jobs = True
    max_tries = 3

    # Scheduled jobs
    cron_jobs = [
        cron(consolidate_memory,   hour=2, minute=0),   # 2 AM daily
        cron(cleanup_expired_uploads, hour=3, minute=0),
    ]
```

---

## Docker Compose

The worker runs as a separate service alongside the app:

```yaml
# docker-compose.yml (addition)
worker:
  build:
    context: .
    dockerfile: docker/Dockerfile
  command: uv run arq app.workers.main.WorkerSettings
  env_file: .env
  depends_on:
    postgres:
      condition: service_healthy
    redis:
      condition: service_healthy
  restart: unless-stopped
```

Scaling: run multiple worker containers for higher throughput. Each pulls jobs from the same Redis queue.

```bash
docker compose up --scale worker=4
```

---

## Job Status API

```
GET /api/v1/jobs/{job_id}
```

```json
{
  "job_id": "abc123",
  "status": "in_progress",
  "queued_at": "2026-08-01T10:00:00Z",
  "started_at": "2026-08-01T10:00:01Z",
  "result": null,
  "error": null
}
```

Document upload returns a `job_id` in the response so clients can poll for completion:

```json
{
  "document": { "id": "...", "status": "processing" },
  "job_id": "abc123"
}
```

---

## Retries and Dead Letter

ARQ retries failed jobs up to `max_tries` times with exponential backoff (2s, 4s, 8s). After all retries are exhausted the job enters `deferred` state and is logged with `ERROR` severity.

A Sentry alert fires on job exhaustion. See [Observability](observability.md).
