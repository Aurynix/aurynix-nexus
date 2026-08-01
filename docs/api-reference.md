# API Reference

Base URL: `http://localhost:8000/api/v1`

Interactive docs (development only): `http://localhost:8000/docs`

All protected endpoints require:
```
Authorization: Bearer <access_token>
```

---

## Health

### GET /health

Liveness check — always returns 200 if the server process is alive.

**Response**
```json
{"status": "ok"}
```

---

### GET /health/ready

Readiness check — verifies connectivity to all backing services.

**Response 200**
```json
{
    "status": "ready",
    "checks": {
        "postgres": "ok",
        "redis": "ok",
        "qdrant": "ok"
    }
}
```

**Response 200 (degraded)**
```json
{
    "status": "degraded",
    "checks": {
        "postgres": "ok",
        "redis": "error",
        "qdrant": "ok"
    }
}
```

---

## Auth

### POST /auth/register

Create a new account and receive tokens.

**Request**
```json
{
    "email": "user@example.com",
    "password": "password123"
}
```

**Response 200**
```json
{
    "access_token": "eyJ...",
    "refresh_token": "eyJ...",
    "token_type": "bearer"
}
```

**Errors**
- `409` — email already registered

```bash
curl -s -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","password":"password123"}'
```

---

### POST /auth/login

Authenticate an existing user.

**Request**
```json
{
    "email": "user@example.com",
    "password": "password123"
}
```

**Response 200** — same shape as `/register`

**Errors**
- `401` — invalid credentials

---

### POST /auth/refresh

Exchange a refresh token for a new access token. The old refresh token is blacklisted.

**Request**
```json
{
    "refresh_token": "eyJ..."
}
```

**Response 200** — new `TokenResponse`

**Errors**
- `401` — invalid or revoked refresh token

---

### POST /auth/logout

Blacklist the current access token. Requires Bearer auth.

**Response 204** — No Content

```bash
curl -s -X POST http://localhost:8000/api/v1/auth/logout \
  -H "Authorization: Bearer $TOKEN"
```

---

### GET /auth/me

Return the current authenticated user's profile.

**Response 200**
```json
{
    "id": "0d5ce3d5-e387-4798-857c-a384ecc40ecb",
    "email": "user@example.com",
    "is_active": true,
    "created_at": "2026-08-01T22:25:34.599232Z"
}
```

---

## Chat

### POST /chat/stream ⚡ SSE

Send a message and receive a streaming AI response via Server-Sent Events.

**Request**
```json
{
    "message": "What does my contract say about termination?",
    "conversation_id": null
}
```

- `conversation_id` — optional UUID. Omit to start a new conversation; pass an existing ID to continue one.

**Response** — `text/event-stream`

Events are emitted in this order:

```
data: {"type": "metadata", "conversation_id": "65614641-3af8-4920-9c8e-8fd42fb7c0da"}

data: {"type": "agent_start", "agent": "ChatGroq"}

data: {"type": "token", "content": "Based"}
data: {"type": "token", "content": " on"}
data: {"type": "token", "content": " your"}
...

data: {"type": "done"}
```

If the agent calls the RAG tool:
```
data: {"type": "tool_start", "tool": "knowledge_base_search", "input": "termination clause"}
data: {"type": "tool_end", "tool": "knowledge_base_search"}
```

If an error occurs during streaming:
```
data: {"type": "error", "detail": "An error occurred during streaming."}
data: {"type": "done"}
```

**SSE event types**

| Type | Fields | Description |
|---|---|---|
| `metadata` | `conversation_id` | First event — new or existing conversation ID |
| `agent_start` | `agent` | LLM call started |
| `token` | `content` | One streamed text token |
| `tool_start` | `tool`, `input` | RAG tool invocation started |
| `tool_end` | `tool` | RAG tool returned |
| `error` | `detail` | Streaming error occurred |
| `ping` | — | Keepalive (every 15s on long responses) |
| `done` | — | Stream complete |

```bash
curl -N http://localhost:8000/api/v1/chat/stream \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message":"Summarize my uploaded documents"}'
```

---

### GET /chat/conversations

List all conversations for the current user, newest first.

**Response 200**
```json
[
    {
        "id": "65614641-3af8-4920-9c8e-8fd42fb7c0da",
        "title": null,
        "status": "active",
        "created_at": "2026-08-01T22:31:17Z",
        "updated_at": "2026-08-01T22:31:17Z"
    }
]
```

---

### GET /chat/conversations/{conversation_id}

Get a conversation with its full message history.

**Response 200**
```json
{
    "id": "65614641-3af8-4920-9c8e-8fd42fb7c0da",
    "title": null,
    "status": "active",
    "created_at": "2026-08-01T22:31:17Z",
    "updated_at": "2026-08-01T22:31:17Z",
    "messages": [
        {
            "id": "2555c2e3-172b-402e-a117-2ad6b91e61aa",
            "role": "user",
            "content": "What can you help me with?",
            "created_at": "2026-08-01T22:31:17Z"
        },
        {
            "id": "...",
            "role": "assistant",
            "content": "I can help you by answering questions...",
            "created_at": "2026-08-01T22:31:18Z"
        }
    ]
}
```

**Errors**
- `404` — conversation not found
- `403` — conversation belongs to another user

---

### DELETE /chat/conversations/{conversation_id}

Delete a conversation and all its messages (cascade).

**Response 204** — No Content

---

## Documents

### POST /documents/upload

Upload a document for RAG ingestion. Returns immediately (`202 Accepted`) — ingestion runs in the background.

**Request** — `multipart/form-data`

| Field | Type | Description |
|---|---|---|
| `file` | binary | PDF, DOCX, or TXT file |

**Supported formats:** `.pdf`, `.docx`, `.txt`

**Response 202**
```json
{
    "id": "a1b2c3d4-...",
    "filename": "contract.pdf",
    "file_type": ".pdf",
    "file_size": 102400,
    "status": "processing",
    "chunk_count": null,
    "error_message": null,
    "created_at": "2026-08-01T22:40:00Z"
}
```

Document `status` transitions: `processing` → `ready` (or `failed` on error).

```bash
curl -s -X POST http://localhost:8000/api/v1/documents/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/path/to/document.pdf"
```

---

### GET /documents

List all documents for the current user.

**Response 200**
```json
{
    "documents": [
        {
            "id": "a1b2c3d4-...",
            "filename": "contract.pdf",
            "file_type": ".pdf",
            "file_size": 102400,
            "status": "ready",
            "chunk_count": 42,
            "error_message": null,
            "created_at": "2026-08-01T22:40:00Z"
        }
    ],
    "total": 1
}
```

---

### GET /documents/{document_id}

Get a single document by ID.

**Errors**
- `404` — document not found
- `403` — document belongs to another user

---

### DELETE /documents/{document_id}

Delete a document record and remove all its vectors from Qdrant.

**Response 204** — No Content

---

## Memory

User facts are automatically extracted from conversations by the `memory_save` node. They can also be managed manually.

### GET /memory

List all memory facts for the current user.

**Response 200**
```json
{
    "facts": [
        {
            "id": "...",
            "key": "role",
            "value": "product manager",
            "source": "auto",
            "confidence": 0.9,
            "created_at": "2026-08-01T22:35:00Z",
            "updated_at": "2026-08-01T22:35:00Z"
        }
    ],
    "total": 1
}
```

---

### POST /memory

Manually create a memory fact.

**Request**
```json
{
    "key": "preferred_language",
    "value": "Python",
    "source": "manual",
    "confidence": 1.0
}
```

**Response 201** — created fact

---

### PUT /memory/{fact_id}

Update an existing memory fact.

**Request** — partial update, all fields optional
```json
{
    "value": "Python and TypeScript",
    "confidence": 0.95
}
```

---

### DELETE /memory/{fact_id}

Delete a memory fact.

**Response 204** — No Content

---

## Error responses

All errors follow a consistent shape:

```json
{
    "detail": "Human-readable error message."
}
```

| Status | Meaning |
|---|---|
| `400` | Bad request / validation error |
| `401` | Not authenticated or token expired |
| `403` | Authenticated but not authorized |
| `404` | Resource not found |
| `409` | Conflict (e.g. duplicate email) |
| `422` | Request validation failed (Pydantic) |
| `500` | Unexpected server error |
| `502` | External service unavailable (Groq, Qdrant) |
