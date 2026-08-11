# Frontend API Reference

Everything you need to build a frontend against Aurynix. All shapes are derived directly from the backend schemas — nothing is guessed.

---

## Basics

```
Base URL:  http://localhost:8000/api/v1
Auth:      Authorization: Bearer <access_token>   (all protected endpoints)
Format:    Content-Type: application/json          (all request bodies)
```

Every protected endpoint returns `401` if the token is missing, expired, or blacklisted.

---

## Error shape

All errors follow the same envelope:

```json
{ "detail": "Human-readable message" }
```

| HTTP code | Meaning |
|---|---|
| `400` | Bad request / validation error |
| `401` | Not authenticated |
| `403` | Authenticated but not allowed |
| `404` | Resource not found |
| `409` | Conflict (e.g. email already exists) |
| `422` | Schema validation failed (body field missing or wrong type) |
| `429` | Rate limit exceeded |
| `500` | Internal server error |

---

## Rate limit headers (every `/api/v1/*` response)

```
X-RateLimit-Limit: 20
X-RateLimit-Remaining: 17
X-RateLimit-Reset: 1754042400     ← Unix timestamp when the window resets
Retry-After: 23                   ← only on 429
```

---

## 1 — Auth

### `POST /auth/register`

No auth required.

**Request:**
```json
{
  "email": "user@example.com",
  "password": "min8chars"
}
```

**Response `200`:**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer"
}
```

**Errors:** `409` email taken · `422` password < 8 chars

---

### `POST /auth/login`

No auth required.

**Request:**
```json
{
  "email": "user@example.com",
  "password": "yourpassword"
}
```

**Response `200`:** same shape as register.

**Errors:** `401` wrong credentials

---

### `POST /auth/refresh`

No auth required.

**Request:**
```json
{ "refresh_token": "eyJ..." }
```

**Response `200`:**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer"
}
```

**Errors:** `401` refresh token expired or invalid

---

### `POST /auth/logout`

**Auth required.** Blacklists the current access token.

No request body. Pass the token in the `Authorization` header as usual.

**Response `204`:** no body.

---

### `GET /auth/me`

**Auth required.**

**Response `200`:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "user@example.com",
  "is_active": true,
  "created_at": "2026-08-11T09:00:00Z"
}
```

---

## 2 — Chat (SSE streaming)

### `POST /chat/stream`

**Auth required.** Returns a Server-Sent Events stream.

**Request:**
```json
{
  "message": "What does my document say about pricing?",
  "conversation_id": null
}
```

| Field | Type | Notes |
|---|---|---|
| `message` | `string` | required |
| `conversation_id` | `UUID \| null` | omit or `null` to start a new conversation; pass an existing UUID to continue |

**Response:** `Content-Type: text/event-stream`

Each line is a JSON object prefixed with `data: `. The stream always ends with a `done` event.

#### SSE event types

```
data: {"type":"metadata","conversation_id":"550e8400-..."}

data: {"type":"agent_start","agent":"ChatGroq"}

data: {"type":"tool_start","tool":"knowledge_base_search","input":"pricing tiers"}

data: {"type":"tool_end","tool":"knowledge_base_search"}

data: {"type":"token","content":"The document mentions"}

data: {"type":"token","content":" three pricing tiers..."}

data: {"type":"interrupt","question":"Do you want me to send this email to John?"}

data: {"type":"error","detail":"An error occurred during streaming."}

data: {"type":"done"}
```

| Event type | When emitted | Key fields |
|---|---|---|
| `metadata` | First event, always | `conversation_id` — save this to continue the conversation |
| `agent_start` | When the LLM starts generating | `agent` — model name |
| `tool_start` | When a tool is called | `tool`, `input` |
| `tool_end` | When a tool returns | `tool` |
| `token` | For each streamed token | `content` — append to your buffer |
| `interrupt` | Agent needs human input | `question` — show to the user; their next message resumes the graph |
| `error` | Stream-level error | `detail` |
| `done` | Always the last event | no extra fields |

**How to consume the stream in JS:**

```js
const res = await fetch('/api/v1/chat/stream', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`,
  },
  body: JSON.stringify({ message, conversation_id }),
});

const reader = res.body.getReader();
const decoder = new TextDecoder();
let buffer = '';
let conversationId = null;

while (true) {
  const { done, value } = await reader.read();
  if (done) break;

  buffer += decoder.decode(value, { stream: true });
  const lines = buffer.split('\n');
  buffer = lines.pop(); // keep incomplete line

  for (const line of lines) {
    if (!line.startsWith('data: ')) continue;
    const event = JSON.parse(line.slice(6));

    if (event.type === 'metadata') conversationId = event.conversation_id;
    if (event.type === 'token') appendToMessage(event.content);
    if (event.type === 'tool_start') showToolIndicator(event.tool);
    if (event.type === 'tool_end') hideToolIndicator();
    if (event.type === 'interrupt') showHumanInputPrompt(event.question);
    if (event.type === 'done') finalizeMessage();
    if (event.type === 'error') showError(event.detail);
  }
}
```

---

### `GET /chat/conversations`

**Auth required.** Returns all conversations for the current user, newest first.

**Response `200`:**
```json
[
  {
    "id": "550e8400-...",
    "title": null,
    "status": "active",
    "created_at": "2026-08-11T09:00:00Z",
    "updated_at": "2026-08-11T09:05:00Z"
  }
]
```

`title` is always `null` currently (not yet generated). `status` is `"active"` or `"interrupted"` (paused at a human handoff).

---

### `GET /chat/conversations/{conversation_id}`

**Auth required.** Returns conversation + all messages.

**Response `200`:**
```json
{
  "id": "550e8400-...",
  "title": null,
  "status": "active",
  "created_at": "2026-08-11T09:00:00Z",
  "updated_at": "2026-08-11T09:05:00Z",
  "messages": [
    {
      "id": "abc123-...",
      "role": "user",
      "content": "What does my document say about pricing?",
      "created_at": "2026-08-11T09:00:01Z"
    },
    {
      "id": "def456-...",
      "role": "assistant",
      "content": "The document mentions three pricing tiers...",
      "created_at": "2026-08-11T09:00:05Z"
    }
  ]
}
```

`role` is `"user"`, `"assistant"`, or `"tool"`.

**Errors:** `404` not found · `403` not yours

---

### `DELETE /chat/conversations/{conversation_id}`

**Auth required.**

**Response `204`:** no body.

**Errors:** `404` · `403`

---

## 3 — Documents

### `POST /documents/upload`

**Auth required.** `multipart/form-data`.

**Request:** send as form data, field name `file`.

```
Content-Type: multipart/form-data

file: <binary content>
```

Supported types: PDF, DOCX, TXT. Max size: 50 MB.

**Response `202`:**
```json
{
  "id": "550e8400-...",
  "filename": "report.pdf",
  "file_type": "pdf",
  "file_size": 204800,
  "status": "processing",
  "chunk_count": null,
  "error_message": null,
  "created_at": "2026-08-11T09:00:00Z",
  "updated_at": "2026-08-11T09:00:00Z",
  "job_id": "arq:job:abc123"
}
```

`job_id` is present if ARQ is available; `null` if the worker fell back to in-process. `status` starts as `"processing"` and becomes `"ready"` or `"failed"` after ingest completes.

---

### `GET /documents/jobs/{job_id}`

**Auth required.** Poll to track ingest progress.

**Response `200`:**
```json
{
  "job_id": "arq:job:abc123",
  "status": "complete",
  "result": {
    "doc_id": "550e8400-...",
    "status": "ready",
    "chunk_count": 47
  }
}
```

`status` values: `"queued"` · `"in_progress"` · `"complete"` · `"not_found"` · `"error"`

**Polling pattern:**
```js
async function waitForIngest(jobId, token) {
  while (true) {
    const res = await fetch(`/api/v1/documents/jobs/${jobId}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await res.json();
    if (data.status === 'complete' || data.status === 'error') return data;
    await new Promise(r => setTimeout(r, 2000)); // poll every 2s
  }
}
```

---

### `GET /documents`

**Auth required.**

**Response `200`:**
```json
{
  "items": [
    {
      "id": "550e8400-...",
      "filename": "report.pdf",
      "file_type": "pdf",
      "file_size": 204800,
      "status": "ready",
      "chunk_count": 47,
      "error_message": null,
      "created_at": "2026-08-11T09:00:00Z",
      "updated_at": "2026-08-11T09:01:30Z",
      "job_id": null
    }
  ],
  "total": 1
}
```

---

### `GET /documents/{document_id}`

**Auth required.**

**Response `200`:** same shape as a single item in the list above.

**Errors:** `404`

---

### `DELETE /documents/{document_id}`

**Auth required.** Deletes the DB row and removes all Qdrant vectors for the document.

**Response `204`:** no body.

**Errors:** `404`

---

## 4 — Memory

The agent reads these facts automatically at the start of every conversation. You can let the agent manage them, or expose a UI for users to view/edit their own memory.

### `GET /memory`

**Auth required.**

**Response `200`:**
```json
[
  {
    "id": "550e8400-...",
    "key": "preferred_language",
    "value": "Arabic",
    "source": "auto",
    "confidence": 0.9,
    "created_at": "2026-08-11T09:00:00Z",
    "updated_at": "2026-08-11T09:00:00Z"
  }
]
```

`source` is `"auto"` (extracted by agent) or `"manual"` (user-created).

---

### `POST /memory`

**Auth required.**

**Request:**
```json
{
  "key": "preferred_language",
  "value": "Arabic",
  "source": "manual",
  "confidence": 1.0
}
```

| Field | Type | Default |
|---|---|---|
| `key` | `string` | required |
| `value` | `string` | required |
| `source` | `"manual" \| "auto"` | `"manual"` |
| `confidence` | `float 0.0–1.0` | `1.0` |

**Response `201`:** full `MemoryFactResponse` object.

---

### `PUT /memory/{fact_id}`

**Auth required.** All fields optional (partial update).

**Request:**
```json
{
  "key": "preferred_language",
  "value": "English",
  "confidence": 0.8
}
```

**Response `200`:** updated fact object.

**Errors:** `404`

---

### `DELETE /memory/{fact_id}`

**Auth required.**

**Response `204`:** no body.

---

## 5 — Google OAuth

### `GET /oauth/google/authorize`

**Auth required.** Call this to start the OAuth flow.

**Response `200`:**
```json
{
  "url": "https://accounts.google.com/o/oauth2/auth?client_id=...&scope=...",
  "state": "abc123xyz"
}
```

**Frontend flow:**
```js
const { url } = await fetch('/api/v1/oauth/google/authorize', {
  headers: { Authorization: `Bearer ${token}` },
}).then(r => r.json());

window.location.href = url; // redirect to Google
```

After the user grants access, Google redirects to your backend callback, which then redirects the browser to `OAUTH_SUCCESS_REDIRECT` (default: `http://localhost:3000/settings?oauth=success`).

---

### `GET /oauth/google/callback`

**No auth.** Called by Google automatically — you never call this directly. The backend handles it and redirects to `OAUTH_SUCCESS_REDIRECT` on success or `OAUTH_ERROR_REDIRECT` on failure (same URL with `?oauth=error&reason=...`).

---

### `GET /oauth/google/status`

**Auth required.** Check if the user has connected Google.

**Response `200` (connected):**
```json
{
  "connected": true,
  "scopes": [
    "openid",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/userinfo.email"
  ]
}
```

**Response `200` (not connected):**
```json
{ "connected": false, "scopes": [] }
```

---

### `DELETE /oauth/google/disconnect`

**Auth required.**

**Response `204`:** no body. Idempotent — safe to call even if not connected.

---

## 6 — Health (no auth)

### `GET /health`

```json
{ "status": "ok" }
```

### `GET /health/ready`

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

`status` is `"ready"` if all checks are `"ok"`, otherwise `"degraded"`.

---

## Token storage pattern (frontend)

```
access_token   → memory (Redux / Zustand / Context)
                 short-lived (60 min default)
                 lost on page refresh → use refresh_token to re-issue

refresh_token  → localStorage or httpOnly cookie
                 long-lived (30 days)
                 use to get a new access_token on app boot or 401
```

**On app boot:**
```js
const refreshToken = localStorage.getItem('refresh_token');
if (refreshToken) {
  const { access_token, refresh_token } = await fetch('/api/v1/auth/refresh', {
    method: 'POST',
    body: JSON.stringify({ refresh_token: refreshToken }),
  }).then(r => r.json());
  setAccessToken(access_token);
  localStorage.setItem('refresh_token', refresh_token);
}
```

---

## What you can build

### Core UI (needed for the app to function)

| Screen | Uses |
|---|---|
| Login / Register | `POST /auth/login`, `POST /auth/register` |
| Chat interface | `POST /chat/stream` (SSE), `GET /chat/conversations` |
| Conversation history | `GET /chat/conversations`, `GET /chat/conversations/{id}` |
| Document library | `GET /documents`, `POST /documents/upload`, `DELETE /documents/{id}` |
| Upload progress | `GET /documents/jobs/{job_id}` polling |

### Settings / Profile

| Feature | Uses |
|---|---|
| My profile | `GET /auth/me` |
| Connect Google | `GET /oauth/google/authorize` + `GET /oauth/google/status` |
| Disconnect Google | `DELETE /oauth/google/disconnect` |
| My memory facts | `GET /memory`, `POST /memory`, `PUT /memory/{id}`, `DELETE /memory/{id}` |

### Power features

| Feature | Uses | Notes |
|---|---|---|
| Agent activity feed | SSE `agent_start`, `tool_start`, `tool_end` events | Show which tool is running in real time |
| Human handoff UI | SSE `interrupt` event | Show a prompt asking the user to confirm/answer; next message resumes the graph |
| Document status badges | `status` field on document + job polling | `processing` → spinner, `ready` → green, `failed` → red |
| Rate limit indicator | `X-RateLimit-Remaining` header | Show a "X requests left this minute" counter on the chat input |
| System health widget | `GET /health/ready` | Show degraded banner if any check fails |

### What the backend does NOT have yet (you'd need to add these if you want them)

| Feature | What's missing |
|---|---|
| Conversation title | `Conversation.title` is always `null` — backend doesn't auto-generate a title from the first message |
| Pagination | `GET /documents` returns all documents, no `limit`/`offset` params |
| File preview | No endpoint to serve or preview uploaded files |
| User profile update | No `PUT /auth/me` — can't change email or password |
| Email/calendar UI | No dedicated endpoints — only through the chat agent |
| Notification when ingest completes | No webhook or WebSocket push — frontend must poll |
| Search conversations | No `GET /chat/conversations?q=...` |
| Shared conversations | Everything is per-user only |
