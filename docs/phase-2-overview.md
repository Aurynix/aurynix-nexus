# Phase 2 — Overview

Phase 1 delivered an AI that can **think and remember**: streaming chat, JWT auth, RAG over uploaded documents, long-term memory via LangGraph, and a full PostgreSQL/Redis/Qdrant stack.

Phase 2 evolves Aurynix into an AI that can **act**: it gains real-world tools (Gmail, Calendar, web search), a production-hardened platform (rate limiting, background workers, observability), and a supervisor multi-agent architecture that routes tasks to specialized sub-agents.

---

## What Was Built

| Track | Components | Depends on |
|---|---|---|
| **Google Tools** | OAuth 2.0 infrastructure, Gmail tool, Calendar tool | Google Cloud Console project |
| **Web Search** | Tavily search tool | `TAVILY_API_KEY` |
| **Human Handoff** | LangGraph `interrupt()` | Phase 1 agent graph |
| **Platform** | Redis rate limiting, ARQ background workers | Existing Redis service |
| **Observability** | OpenTelemetry traces, Prometheus metrics, Sentry errors | Docker Compose |
| **Multi-Agent** | Supervisor graph, specialized sub-agents | Phase 1 graph + new tools |

---

## Final Architecture (after Phase 2)

```
                         Frontend / Clients
                                │
                          FastAPI API
                                │
                  JWT auth + Rate Limiter (Redis)
                                │
                     LangGraph Supervisor Agent
                                │
         ┌──────────┬──────────┬──────────┬──────────┐
         │          │          │          │          │
    research      email     calendar   (future)   FINISH
      agent       agent      agent
         │          │          │
      RAG +      Gmail API  Calendar API
    web search
```

---

## New Environment Variables

```bash
# Google OAuth
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/oauth/google/callback
OAUTH_SUCCESS_REDIRECT=http://localhost:3000/settings?oauth=success

# Web Search
TAVILY_API_KEY=tvly-...

# Rate Limiting
RATE_LIMIT_CHAT=20
RATE_LIMIT_AUTH=10
RATE_LIMIT_DOCUMENTS=30
RATE_LIMIT_DEFAULT=60

# Observability
SENTRY_DSN=https://...
SENTRY_TRACES_SAMPLE_RATE=0.1
OTLP_ENDPOINT=http://localhost:4317
```

---

## New API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/oauth/google/authorize` | Start Google OAuth flow |
| `GET` | `/api/v1/oauth/google/callback` | OAuth callback, store tokens |
| `GET` | `/api/v1/oauth/google/status` | Check Google connection status |
| `DELETE` | `/api/v1/oauth/google/disconnect` | Remove stored Google tokens |
| `GET` | `/api/v1/documents/jobs/{job_id}` | Poll ARQ ingest job status |
| `GET` | `/metrics` | Prometheus metrics scrape endpoint |

---

## Document Index

| Document | What it covers |
|---|---|
| [OAuth](oauth.md) | Google OAuth 2.0 setup, token storage, encryption |
| [Tools](tools.md) | Gmail, Calendar, Web Search, Human Handoff, plugin architecture |
| [Rate Limiting](rate-limiting.md) | Redis sliding-window rate limiter |
| [Background Workers](workers.md) | ARQ worker pool, ingest job, fallback behavior |
| [Observability](observability.md) | OpenTelemetry, Prometheus, Sentry |
| [Multi-Agent](multi-agent.md) | Supervisor graph, sub-agents, routing |
