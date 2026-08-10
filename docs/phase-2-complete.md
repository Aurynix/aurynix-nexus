# Phase 2 — What Was Built

This document is a concise record of everything delivered on the `feat/phase-2` branch, intended as a PR reference and onboarding aid.

---

## Starting point

Phase 1 (`main`) delivered:

- FastAPI app with JWT auth (register / login / refresh / logout)
- Streaming chat via SSE, backed by a single LangGraph ReAct agent
- RAG pipeline: PDF/DOCX/TXT upload → chunking → FastEmbed → Qdrant search
- Long-term memory: LangGraph `AsyncPostgresStore` persists user facts across conversations
- Postgres + Redis + Qdrant stack, fully Dockerized

Phase 2 took that foundation and gave the agent **real-world tools**, a **multi-agent architecture**, and **production-grade platform features**.

---

## What was added

### 1 — Web search + tool registry

| File | What it does |
|---|---|
| `app/tools/web_search.py` | Tavily search tool, async, graceful no-op if key missing |
| `app/tools/registry.py` | `make_tools(user_id, db)` factory — returns the right tool set per request |

`make_tools` always includes RAG search, web search, and human handoff. Gmail and Calendar tools are appended only when a DB session is available (they need to look up the OAuth token row).

---

### 2 — Rate limiting

| File | What it does |
|---|---|
| `app/api/middleware.py` | `RateLimitMiddleware` — Redis sliding-window per user+group |
| `app/core/config.py` | `RATE_LIMIT_CHAT`, `RATE_LIMIT_AUTH`, `RATE_LIMIT_DOCUMENTS`, `RATE_LIMIT_DEFAULT` |

Unauthenticated requests fall back to IP-scoped keys. Fails open if Redis is unavailable.

---

### 3 — Google OAuth 2.0

| File | What it does |
|---|---|
| `app/models/oauth_token.py` | `OAuthToken` ORM model — one row per user per provider |
| `app/core/crypto.py` | AES-256-GCM encrypt/decrypt using SHA-256 of `SECRET_KEY` |
| `app/core/google_auth.py` | Authorization URL generation, code exchange, credential restore |
| `app/api/v1/oauth.py` | 4 endpoints: authorize, callback, status, disconnect |
| `alembic/versions/0002_add_oauth_tokens.py` | Migration: creates `oauth_tokens` table |

OAuth state is stored in Redis (`oauth:state:{state}` → user_id, 10-min TTL) to prevent CSRF. Tokens are stored encrypted; rotating `SECRET_KEY` invalidates all stored tokens.

**Endpoints:**

```
GET  /api/v1/oauth/google/authorize    → { url, state }
GET  /api/v1/oauth/google/callback     → 302 to OAUTH_SUCCESS_REDIRECT
GET  /api/v1/oauth/google/status       → { connected, scopes }
DELETE /api/v1/oauth/google/disconnect → 204
```

---

### 4 — Gmail, Calendar, and human handoff tools

| File | What it does |
|---|---|
| `app/tools/gmail.py` | Gmail list/search/read/send/reply via Google API v1 |
| `app/tools/calendar.py` | Calendar list/get/create/delete via Google Calendar API v3 |
| `app/tools/human_handoff.py` | LangGraph `interrupt()` — pauses graph, waits for user reply |

All Google API calls run in `asyncio.to_thread` (the SDK is synchronous). Both tools check for a valid `OAuthToken` row at call time and return a friendly error if the user hasn't connected Google.

---

### 5 — Background workers (ARQ)

| File | What it does |
|---|---|
| `app/workers/tasks.py` | `ingest_document` — opens own DB connection, runs RAGPipeline, updates Document.status |
| `app/workers/settings.py` | `WorkerSettings` — ARQ config (max_jobs=10, timeout=300s) |
| `app/services/document.py` | `_enqueue_ingest()` — tries ARQ, falls back to `asyncio.create_task` |
| `app/schemas/document.py` | `DocumentResponse.job_id` field added |
| `app/api/v1/documents.py` | `GET /documents/jobs/{job_id}` — poll ARQ job status |

Document upload returns `202` immediately with a `job_id`. The worker updates `Document.status` to `ready` or `failed` asynchronously.

**Run the worker:**
```bash
uv run python -m arq app.workers.settings.WorkerSettings
# or via Docker Compose:
docker compose up worker
```

---

### 6 — Observability

| File | What it does |
|---|---|
| `app/core/telemetry.py` | `setup_tracing(app)` — OTel OTLP gRPC, no-op if `OTLP_ENDPOINT` empty; `setup_sentry()` — no-op if `SENTRY_DSN` empty |
| `app/core/metrics.py` | Prometheus counters, histograms, gauge; `GET /metrics` scrape handler |

**Metrics exposed:**

| Metric | Type |
|---|---|
| `aurynix_chat_requests_total` | Counter (label: status) |
| `aurynix_auth_requests_total` | Counter (labels: endpoint, status) |
| `aurynix_document_ingestions_total` | Counter (label: status) |
| `aurynix_tool_calls_total` | Counter (label: tool_name) |
| `aurynix_rate_limit_rejections_total` | Counter (label: group) |
| `aurynix_chat_latency_seconds` | Histogram |
| `aurynix_ingest_duration_seconds` | Histogram |
| `aurynix_active_sse_connections` | Gauge |

---

### 7 — Multi-agent supervisor architecture

| File | What it does |
|---|---|
| `app/agents/state.py` | Added `next_agent: str \| None` field |
| `app/agents/supervisor.py` | `supervisor_node` — structured LLM output picks the next sub-agent |
| `app/agents/subagents.py` | `make_subagent_node(name)` — factory for research / email / calendar agents |
| `app/agents/graphs.py` | Complete rewrite: supervisor topology replacing the Phase 1 ReAct loop |

**Graph topology:**
```
START → memory_load → supervisor
                          │
           ┌──────────────┼──────────────┐
           ▼              ▼              ▼
    research_agent   email_agent  calendar_agent
           │              │              │
           └──────────────┴──────────────┘
                          │
                     supervisor  ← loops (max 15 iterations)
                          │
                     memory_save → END
```

Sub-agents execute tools inline and run a synthesis LLM call before handing back to the supervisor.

---

## Tests added

| File | Covers |
|---|---|
| `tests/unit/test_crypto.py` | AES-256-GCM roundtrip, nonce uniqueness |
| `tests/unit/test_supervisor.py` | `route_supervisor` routing, `SupervisorDecision` model |
| `tests/integration/test_oauth_endpoints.py` | Auth guards, status (not connected), disconnect (204) |
| `tests/unit/test_agents.py` | Updated `_make_state()` with `next_agent` field |

---

## New environment variables

```bash
# Google OAuth
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/oauth/google/callback
OAUTH_SUCCESS_REDIRECT=http://localhost:3000/settings?oauth=success

# Web search
TAVILY_API_KEY=

# Rate limiting
RATE_LIMIT_CHAT=20
RATE_LIMIT_AUTH=10
RATE_LIMIT_DOCUMENTS=30
RATE_LIMIT_DEFAULT=60

# Observability
OTLP_ENDPOINT=
SENTRY_DSN=
SENTRY_TRACES_SAMPLE_RATE=0.1
```

---

## New dependencies

```
tavily-python        web search
cryptography         AES-256-GCM token encryption
google-auth-oauthlib OAuth 2.0 flow
google-api-python-client  Gmail + Calendar APIs
arq                  Redis-backed background workers
opentelemetry-*      distributed tracing (OTLP/gRPC)
prometheus-client    /metrics scrape endpoint
sentry-sdk[fastapi]  error tracking
```

---

## Documentation

All Phase 2 features have dedicated docs in `docs/`:

- [oauth.md](oauth.md) — Google OAuth setup and flow
- [tools.md](tools.md) — Gmail, Calendar, web search, human handoff
- [workers.md](workers.md) — ARQ background workers
- [observability.md](observability.md) — OTel, Prometheus, Sentry
- [rate-limiting.md](rate-limiting.md) — sliding-window rate limiter
- [multi-agent.md](multi-agent.md) — supervisor graph and sub-agents
- [phase-2-overview.md](phase-2-overview.md) — high-level summary

---

## What's next (Phase 3 ideas)

- Parallel sub-agent dispatch via LangGraph `Send` (email + calendar simultaneously)
- Token refresh background job (proactively refresh OAuth tokens before expiry)
- Streaming sub-agent progress events to the SSE client
- Admin dashboard for user/document/job management
- Horizontal scaling: multiple app containers sharing one Redis + Postgres
