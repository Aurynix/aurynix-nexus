# Architecture

## System Overview

```
Client
  │
  ▼
FastAPI (app/main.py)
  ├── Auth endpoints    → JWT issued, Redis blacklist on logout
  ├── Chat /stream      → SSE — streams LangGraph events token by token
  ├── Documents /upload → background RAG ingestion task
  └── Memory CRUD       → user fact management
  │
  ├── PostgreSQL        → users, conversations, messages, documents, memory_facts
  ├── Redis             → JWT token blacklist (JTI → TTL)
  ├── Qdrant            → vector embeddings (per-user filtered)
  └── LangGraph
        ├── Checkpointer (AsyncPostgresStore) → conversation history per thread
        └── Memory Store (AsyncPostgresStore) → long-term user facts
```

---

## Directory Structure

```
aurynix-nexus/
├── app/
│   ├── api/
│   │   ├── middleware.py          # request ID injection
│   │   └── v1/
│   │       ├── router.py          # aggregates all v1 routers
│   │       ├── health.py          # liveness + readiness checks
│   │       ├── auth.py            # register / login / refresh / logout / me
│   │       ├── chat.py            # SSE stream + conversation CRUD
│   │       ├── documents.py       # upload / list / get / delete
│   │       └── memory.py          # memory fact CRUD
│   │
│   ├── agents/
│   │   ├── state.py               # AgentState TypedDict
│   │   ├── nodes.py               # memory_load, agent, tools, memory_save nodes
│   │   ├── router.py              # conditional edge: tools / memory_save / end
│   │   └── graphs.py              # compiled LangGraph workflow
│   │
│   ├── core/
│   │   ├── config.py              # Pydantic Settings (reads .env)
│   │   ├── logging.py             # structlog setup
│   │   ├── exceptions.py          # AurynixError hierarchy
│   │   ├── security.py            # JWT helpers, bcrypt hashing
│   │   ├── llm.py                 # Groq LLM singleton
│   │   └── dependencies.py        # FastAPI DI (CurrentUser, DbSession, RedisClient)
│   │
│   ├── database/
│   │   ├── postgres.py            # async SQLAlchemy engine + session factory
│   │   ├── redis.py               # Redis pool
│   │   └── qdrant.py              # Qdrant async client + ensure_collection()
│   │
│   ├── memory/
│   │   ├── checkpointer.py        # AsyncPostgresSaver via connection pool
│   │   └── store.py               # AsyncPostgresStore via connection pool + fact helpers
│   │
│   ├── models/                    # SQLAlchemy ORM models
│   │   ├── base.py                # Base, TimestampMixin
│   │   ├── user.py
│   │   ├── conversation.py        # Conversation + Message
│   │   ├── document.py
│   │   └── memory.py              # MemoryFact
│   │
│   ├── rag/
│   │   ├── loader.py              # PDF / DOCX / TXT → LangChain Documents
│   │   ├── chunker.py             # RecursiveCharacterTextSplitter (1000/200)
│   │   ├── embedder.py            # FastEmbed (BAAI/bge-small-en-v1.5, local)
│   │   ├── retriever.py           # Qdrant cosine search, score ≥ 0.70, top-5
│   │   └── pipeline.py            # end-to-end ingest + query + delete
│   │
│   ├── schemas/                   # Pydantic v2 request/response models
│   ├── services/                  # Business logic (auth, chat, document, memory)
│   ├── tools/
│   │   └── rag_tool.py            # @tool factory — closes over user_id per request
│   ├── utils/
│   └── main.py                    # create_app() + lifespan
│
├── alembic/                       # DB migrations
├── scripts/
│   ├── init_db.py                 # run migrations + setup Qdrant + LangGraph
│   └── ingest_docs.py             # CLI batch ingestion tool
├── tests/
├── docker/
│   ├── Dockerfile                 # multi-stage production image
│   └── Dockerfile.dev
└── docker-compose.yml
```

---

## Request lifecycle — Chat stream

```
POST /api/v1/chat/stream
        │
        ├─ 1. JWT verified (dependencies.py → get_current_user)
        │       Redis checked for blacklisted JTI
        │
        ├─ 2. Conversation created or loaded (PostgreSQL)
        │
        ├─ 3. User message persisted to messages table
        │
        ├─ 4. LangGraph graph.astream_events() called
        │       │
        │       ├─ memory_load node
        │       │     reads user facts from AsyncPostgresStore
        │       │
        │       ├─ agent node
        │       │     builds system prompt with user facts
        │       │     calls Groq llama-3.3-70b-versatile
        │       │     streams tokens → SSE "token" events
        │       │
        │       ├─ [if tool_calls] → tools node
        │       │     make_rag_tool(user_id) called per-request
        │       │     Qdrant search, results returned to agent
        │       │     loops back to agent node
        │       │
        │       └─ memory_save node
        │             LLM extracts facts from conversation
        │             upserts to AsyncPostgresStore
        │
        └─ 5. Full assistant response persisted to messages table
```

---

## Database connection strategy

Three separate PostgreSQL connections are used intentionally:

| Layer | Driver | URL format | Purpose |
|---|---|---|---|
| SQLAlchemy (app) | asyncpg | `postgresql+asyncpg://` | All ORM queries |
| Alembic (migrations) | psycopg2 | `postgresql+psycopg2://` | Sync-only migration tool |
| LangGraph (checkpointer + store) | psycopg3 via pool | `postgresql://` | Checkpoint + memory tables |

The LangGraph connection uses `AsyncConnectionPool` (from `psycopg_pool`) with `max_size=5` and `autocommit=True`. A bare single connection was not used because it closes unexpectedly under idle timeout.

---

## Key design decisions

**workers=1**
The compiled LangGraph graph is stored as a singleton on `app.state`. Uvicorn must run with a single worker — scale horizontally (multiple containers) rather than increasing workers per process.

**Per-request RAG tool factory**
`make_rag_tool(user_id)` is called at graph execution time, not at startup. This closes over the actual `user_id` from the request instead of a static placeholder. LangGraph's built-in `ToolNode` was not used because it bakes tools at compile time.

**Background document ingestion**
`POST /documents/upload` returns `202 Accepted` immediately. Ingestion (load → chunk → embed → upsert Qdrant) runs in `asyncio.create_task()`. The background task creates its own DB engine because it cannot share the request's session.

**SSE keepalive**
A `ping` event type is defined in `SSEEvent` for keepalive (every 15s). This prevents nginx/load balancer idle timeout on long-running streams.
