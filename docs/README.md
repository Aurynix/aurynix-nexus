# Aurynix Nexus — Documentation

AI-powered business assistant with streaming chat, RAG, long-term memory, multi-agent workflows, and real-world tool integrations.

## Phase 1 — Core Platform

| Document | Description |
|---|---|
| [Getting Started](getting-started.md) | Installation, local setup, first run |
| [Architecture](architecture.md) | System design, data flow, component map |
| [Configuration](configuration.md) | All environment variables explained |
| [API Reference](api-reference.md) | Every endpoint with request/response examples |
| [RAG Pipeline](rag-pipeline.md) | Document ingestion and retrieval internals |
| [Agent System](agents.md) | LangGraph graph, nodes, memory, tools |
| [Authentication](auth.md) | JWT flow, token lifecycle, Redis blacklist |
| [Deployment](deployment.md) | Docker, production checklist |

## Phase 2 — Tools, Platform, Multi-Agent

| Document | Description |
|---|---|
| [Phase 2 Overview](phase-2-overview.md) | What is being built, final architecture, new env vars |
| [OAuth](oauth.md) | Google OAuth 2.0 — setup, token storage, refresh |
| [Tools](tools.md) | Gmail, Calendar, Web Search, Human Handoff, plugin guide |
| [Rate Limiting](rate-limiting.md) | Redis sliding-window rate limiter |
| [Caching](caching.md) | Redis LLM response cache and embedding cache |
| [Background Workers](workers.md) | ARQ worker pool, job types, retry policy |
| [Observability](observability.md) | OpenTelemetry traces, Prometheus metrics, Sentry |
| [Multi-Agent](multi-agent.md) | Supervisor graph, sub-agents, routing, extensibility |

## Quick Links

- Interactive API docs (dev only): `http://localhost:8000/docs`
- Health check: `GET /api/v1/health/ready`
- Main chat endpoint: `POST /api/v1/chat/stream` (SSE)
- Grafana dashboard (Phase 2): `http://localhost:3000`
- Jaeger traces (Phase 2): `http://localhost:16686`
