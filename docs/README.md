# Aurynix Nexus — Documentation

AI-powered business assistant with streaming chat, RAG, long-term memory, and multi-agent workflows.

## Contents

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

## Quick Links

- Interactive API docs (dev only): `http://localhost:8000/docs`
- Health check: `GET /api/v1/health/ready`
- Main chat endpoint: `POST /api/v1/chat/stream` (SSE)
