# Phase 2 — Overview

Phase 1 delivered an AI that can **think and remember**: streaming chat, JWT auth, RAG over uploaded documents, long-term memory via LangGraph, and a full PostgreSQL/Redis/Qdrant stack.

Phase 2 evolves Aurynix into an AI that can **act**: it gains real-world tools (Gmail, Calendar, web search), a production-hardened platform (rate limiting, caching, background workers, observability), and a supervisor multi-agent architecture that routes tasks to specialized sub-agents.

---

## What is Being Built

| Track | Components | Depends on |
|---|---|---|
| **Google Tools** | OAuth 2.0 infrastructure, Gmail tool, Calendar tool | Google Cloud Console project |
| **Web Search** | Tavily search tool | `TAVILY_API_KEY` |
| **Human Handoff** | LangGraph `interrupt()`, ticket model, notify webhook | Phase 1 agent graph |
| **Platform** | Redis rate limiting, Redis LLM cache, ARQ workers | Existing Redis service |
| **Observability** | OpenTelemetry traces, Prometheus metrics, Sentry errors | Docker Compose |
| **Multi-Agent** | Supervisor graph, specialized sub-agents | Phase 1 graph + new tools |

---

## Final Architecture (after Phase 2)

```
                         Frontend / Clients
                                │
                          FastAPI API
                                │
                      JWT + OAuth middleware
                                │
                        Rate Limiter (Redis)
                                │
                     LangGraph Supervisor Agent
                                │
         ┌──────────┬──────────┬──────────┬──────────┐
         │          │          │          │          │
      Memory      RAG       Gmail     Calendar   WebSearch
   (Postgres)  (Qdrant)    Agent      Agent       Agent
         │          │          │          │          │
    Redis cache  Documents  Gmail API  Google API  Tavily
                                │
                         Human Handoff
                                │
                        Ticket / Webhook
```

---

## New Environment Variables (summary)

```bash
# Google OAuth
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/oauth/google/callback

# Web Search
TAVILY_API_KEY=tvly-...

# Workers
WORKER_CONCURRENCY=4
WORKER_MAX_JOBS=10

# Rate Limiting
RATE_LIMIT_PER_MINUTE=60
RATE_LIMIT_BURST=10

# Caching
LLM_CACHE_TTL_SECONDS=300

# Observability
SENTRY_DSN=https://...
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
```

Full reference: [Configuration](configuration.md)

---

## New API Endpoints (summary)

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/oauth/google/authorize` | Start Google OAuth flow |
| `GET` | `/api/v1/oauth/google/callback` | OAuth callback, store tokens |
| `DELETE` | `/api/v1/oauth/google/revoke` | Revoke stored Google tokens |
| `GET` | `/api/v1/oauth/google/status` | Check connection status |

Full reference: [API Reference](api-reference.md)

---

## Document Index

| Document | What it covers |
|---|---|
| [OAuth](oauth.md) | Google OAuth 2.0 setup, token storage, refresh flow |
| [Tools](tools.md) | Gmail, Calendar, Web Search, Human Handoff, plugin architecture |
| [Rate Limiting](rate-limiting.md) | Redis sliding-window rate limiter |
| [Caching](caching.md) | Redis LLM response cache |
| [Background Workers](workers.md) | ARQ worker pool, job types, retry policy |
| [Observability](observability.md) | OpenTelemetry, Prometheus, Sentry |
| [Multi-Agent](multi-agent.md) | Supervisor graph, sub-agents, routing |
