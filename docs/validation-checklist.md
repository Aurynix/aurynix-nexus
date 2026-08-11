# Phase 2 Validation Checklist

Work through each section in order. Mark each item `[x]` when confirmed working, `[!]` when a bug is found (add a note inline). When every item in a section is green, move to the next.

**Environment required:** all services running (`docker compose up -d`) + valid `.env` with real API keys.

---

## 0 — Smoke Test (before anything else)

```bash
curl http://localhost:8000/api/v1/health/ready
# expected: {"status":"ready","checks":{"postgres":"ok","redis":"ok","qdrant":"ok"}}
```

- [ ] Health check returns `ready`
- [ ] Postgres reachable
- [ ] Redis reachable
- [ ] Qdrant reachable
- [ ] Worker process running (`docker compose ps worker`)

---

## 1 — Auth

### Happy path

- [ ] `POST /auth/register` — new user, returns `access_token` + `refresh_token`
- [ ] `POST /auth/login` — correct credentials, returns tokens
- [ ] `POST /auth/refresh` — valid refresh token, returns new `access_token`
- [ ] `POST /auth/logout` — token blacklisted, subsequent requests return `401`
- [ ] `GET /auth/me` — returns user profile for valid token

### Error paths

- [ ] Register with existing email → `409 Conflict`
- [ ] Login with wrong password → `401`
- [ ] Login with non-existent email → `401`
- [ ] Protected endpoint with no token → `401`
- [ ] Protected endpoint with malformed token → `401`
- [ ] Protected endpoint with expired token → `401`
- [ ] Protected endpoint with blacklisted token (after logout) → `401`
- [ ] `POST /auth/refresh` with an access token instead of refresh token → `401`

---

## 2 — RAG + Background Worker

### Happy path

```
Upload PDF → 202 + job_id → poll GET /documents/jobs/{job_id} → status=complete → ask question → get answer
```

- [ ] `POST /documents/upload` returns `202` immediately (not waiting for ingest)
- [ ] Response body contains `job_id`
- [ ] `GET /documents/jobs/{job_id}` returns `status: queued` or `in_progress` while processing
- [ ] `GET /documents/jobs/{job_id}` returns `status: complete` after worker finishes
- [ ] `GET /documents/{id}` shows `status: ready` and correct `chunk_count`
- [ ] Chat: "What does the document say about X?" → answer drawn from document (not hallucinated)
- [ ] `DELETE /documents/{id}` — document row deleted, Qdrant vectors deleted
- [ ] After delete, same question returns "no relevant documents found" (not old answer)

### Error paths

- [ ] Upload non-supported file type → `422` or informative error
- [ ] Upload file larger than limit → rejected cleanly
- [ ] `GET /documents/jobs/{fake_job_id}` → `status: not_found` (not 500)
- [ ] Worker fails mid-ingest (e.g. Qdrant down) → `Document.status = failed`, `error_message` populated
- [ ] ARQ unavailable at upload time → falls back to `asyncio.create_task`, no `job_id` in response, ingest still completes

---

## 3 — Rate Limiting

- [ ] Sending 25 chat requests rapidly → first 20 succeed, remaining return `429`
- [ ] `429` response includes `Retry-After` header
- [ ] `429` response includes `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` headers
- [ ] Successful requests include `X-RateLimit-Remaining` header
- [ ] Rate limit resets after 60 seconds
- [ ] Unauthenticated requests to `/auth/*` are rate-limited by IP (not user)
- [ ] Redis down → rate limit fails open (requests pass through, no 500)

---

## 4 — Google OAuth

### Connect flow

- [ ] `GET /oauth/google/authorize` → returns `{ url, state }` (requires JWT)
- [ ] `GET /oauth/google/authorize` without JWT → `401`
- [ ] Visiting `url` redirects to Google consent screen
- [ ] After consent, callback redirects to `OAUTH_SUCCESS_REDIRECT`
- [ ] `GET /oauth/google/status` → `{ connected: true, scopes: [...] }`
- [ ] `oauth_tokens` table has one row for the user

### Disconnect flow

- [ ] `DELETE /oauth/google/disconnect` → `204`
- [ ] `GET /oauth/google/status` → `{ connected: false, scopes: [] }`
- [ ] `oauth_tokens` row deleted

### Error paths

- [ ] Callback with wrong `state` → rejected (CSRF protection)
- [ ] Callback with expired `state` (after 10 min) → rejected
- [ ] Callback with `error=access_denied` (user clicked deny) → handled gracefully, no 500
- [ ] `DELETE /oauth/google/disconnect` when not connected → `204` (idempotent)
- [ ] Reconnect (connect again when already connected) → old token row replaced, not duplicated

---

## 5 — Gmail Tool

> Requires Google account connected via OAuth.

### Happy path

- [ ] Chat: "Show me my last 5 emails" → list with sender, subject, date
- [ ] Chat: "Search for emails from john@example.com" → filtered results
- [ ] Chat: "Read the email from John about the invoice" → full body returned
- [ ] Chat: "Send an email to test@example.com saying hello" → email delivered (check inbox)
- [ ] Chat: "Reply to John's email saying thanks" → reply appears in thread

### Error paths

- [ ] Gmail tool called when user has no OAuth token → friendly message ("Connect your Google account first"), not a stack trace
- [ ] Gmail API returns error (e.g. invalid message_id) → agent handles gracefully, does not crash
- [ ] OAuth token expired → tool attempts refresh; if refresh fails, friendly error returned

---

## 6 — Google Calendar Tool

> Requires Google account connected via OAuth.

### Happy path

- [ ] Chat: "What's on my calendar this week?" → list of upcoming events
- [ ] Chat: "Get details for my 3pm meeting" → full event details
- [ ] Chat: "Create a meeting tomorrow at 2pm called Team Sync" → event created (verify in Google Calendar)
- [ ] Chat: "Delete the Team Sync meeting" → event deleted (verify in Google Calendar)
- [ ] Chat: "List all my calendars" → calendar list returned

### Error paths

- [ ] Calendar tool called when user has no OAuth token → friendly message, not crash
- [ ] Create event with invalid date format → agent handles gracefully
- [ ] Delete non-existent event → informative error, not 500

---

## 7 — Web Search Tool

- [ ] Chat: "What happened in AI news today?" → Tavily results returned and summarized
- [ ] Chat: "Search the web for FastAPI best practices" → relevant results
- [ ] Results include source URLs
- [ ] `TAVILY_API_KEY` missing → graceful error message ("Web search is not available"), not crash
- [ ] Tavily API timeout → graceful error, agent continues without search result

---

## 8 — Human Handoff

- [ ] Chat: ask something ambiguous like "Delete all my emails" → agent calls `request_human_input` before acting
- [ ] SSE stream emits `done` event while graph is paused (waiting for input)
- [ ] Next message to same `conversation_id` resumes graph from interrupt point
- [ ] Agent uses the human's reply to complete the task

---

## 9 — Multi-Agent Supervisor

### Routing

- [ ] "Search my documents for X" → routed to `research_agent` (check logs)
- [ ] "Show me my inbox" → routed to `email_agent`
- [ ] "What's on my calendar?" → routed to `calendar_agent`
- [ ] "What time is it?" (no tools needed) → supervisor returns `FINISH` without calling a sub-agent

### Cross-domain request (key test)

```
"Search my emails for John's invoice and add a reminder to my calendar to follow up tomorrow."
```

- [ ] Supervisor routes to `email_agent` first
- [ ] Email agent finds and reads the invoice email
- [ ] Supervisor routes to `calendar_agent` next
- [ ] Calendar agent creates the reminder event
- [ ] Final response synthesizes both results coherently

### Safety

- [ ] Supervisor exits after 15 iterations (not infinite loop)
- [ ] `iteration_count` visible in logs/state
- [ ] No sub-agent silently swallows a tool error (errors surface in messages)

---

## 10 — Observability

### Prometheus

- [ ] `GET /metrics` returns `200` with `text/plain; version=0.0.4` content-type
- [ ] `aurynix_chat_requests_total` increments after a chat request
- [ ] `aurynix_rate_limit_rejections_total` increments after a `429`
- [ ] `aurynix_active_sse_connections` goes up during a stream, back down after

### OpenTelemetry (if `OTLP_ENDPOINT` set)

- [ ] Traces appear in Jaeger / Grafana Tempo after a chat request
- [ ] Trace shows FastAPI root span with child spans for DB queries
- [ ] No errors in app logs related to OTLP exporter

### Sentry (if `SENTRY_DSN` set)

- [ ] Intentionally trigger a 500 (e.g. bad DB query) → error appears in Sentry
- [ ] Event includes stack trace and `user_id` context

### Logs

- [ ] All logs are structured JSON in production mode (`ENVIRONMENT=production`)
- [ ] `request_id` present on every log line within a request
- [ ] No raw stack traces in logs (errors logged as structured fields)

---

## 11 — End-to-End Flow (full system)

Run this sequence without restarting anything:

1. [ ] Register a new user
2. [ ] Upload a PDF
3. [ ] Wait for ingest to complete (poll job status)
4. [ ] Connect Google OAuth
5. [ ] Ask: "Summarize my document and check if I have any meetings about it this week"
   - [ ] RAG retrieval happens
   - [ ] Calendar checked
   - [ ] Coherent answer combining both
6. [ ] Ask: "Search the web for the latest news on [topic from document]"
   - [ ] Tavily results returned
7. [ ] Logout
8. [ ] Confirm old token is blacklisted

---

## Gaps Found

Document any failures here as they're discovered:

| # | Section | Description | Status |
|---|---|---|---|
| 1 | | | |
| 2 | | | |

---

## Sign-off

- [ ] All sections above completed with no open `[!]` items
- [ ] CI passes on `feat/phase-2` (`ruff check` + `pytest`)
- [ ] `feat/phase-2` → `main` PR ready
