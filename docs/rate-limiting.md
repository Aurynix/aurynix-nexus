# Rate Limiting

Aurynix enforces per-user rate limits using a Redis sliding-window counter. Limits are applied at the middleware layer before any business logic runs.

---

## How It Works

Each request increments a Redis key scoped to `user_id + endpoint_group` (or `ip + group` for unauthenticated requests). If the count exceeds the limit within the window, the request is rejected immediately with `429 Too Many Requests`.

```
Request arrives
      │
Extract user_id from JWT (or fall back to IP)
      │
      ▼
INCR  ratelimit:{scope}:{group}:{window}
      │
EXPIRE key to 90s (if new key)
      │
      ▼
count > limit?
  ├── No  → pass through to handler
  └── Yes → 429 { "detail": "Rate limit exceeded. Retry after N seconds." }
```

**Fail-open:** If Redis is unavailable, the middleware passes all requests through instead of blocking them.

### Redis key structure

```
ratelimit:550e8400-e29b...:chat:1754042340
          └──────────────┘ └──┘ └────────┘
               user_id     group  window
                                 (Unix minute)
```

Unauthenticated requests use `ip:{client_ip}` in place of the user_id.

The window is the current Unix timestamp floored to the nearest minute — a new counter starts each minute automatically.

---

## Limits by Endpoint Group

| Group | Endpoints | Default limit |
|---|---|---|
| `chat` | `/api/v1/chat/*` | 20 req/min |
| `auth` | `/api/v1/auth/*` | 10 req/min |
| `documents` | `/api/v1/documents/*` | 30 req/min |
| `default` | All other `/api/v1/*` endpoints | 60 req/min |

All limits are configurable via environment variables:

```bash
RATE_LIMIT_CHAT=20
RATE_LIMIT_AUTH=10
RATE_LIMIT_DOCUMENTS=30
RATE_LIMIT_DEFAULT=60
```

---

## Implementation

### Middleware (`app/api/middleware.py`)

```python
class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith("/api/v1/"):
            return await call_next(request)

        user_id = _extract_user_id(request)   # from JWT, or None
        scope = user_id if user_id else f"ip:{request.client.host}"

        group = _rate_limit_group(path)
        limit = _rate_limit_for_group(group)
        window = int(time.time() // 60)
        key = f"ratelimit:{scope}:{group}:{window}"

        try:
            redis = await get_redis()
            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, 90)  # 90s TTL — covers the minute boundary
        except Exception:
            return await call_next(request)   # fail open if Redis is down

        if count > limit:
            rate_limit_rejections_total.labels(group=group).inc()
            retry_after = reset_ts - int(time.time())
            return JSONResponse(
                {"detail": f"Rate limit exceeded. Retry after {retry_after}s."},
                status_code=429,
                headers={"Retry-After": str(retry_after), ...},
            )

        return await call_next(request)
```

### Response headers

Every request to a `/api/v1/` route (whether limited or not) receives:

```
X-RateLimit-Limit: 20
X-RateLimit-Remaining: 17
X-RateLimit-Reset: 1754042400
Retry-After: 23          ← only on 429
```

---

## Unauthenticated Endpoints

Routes that don't carry a valid JWT (login, register, OAuth callback) are rate-limited by IP address:

```
ratelimit:ip:192.168.1.1:auth:1754042340
```

This prevents credential stuffing without requiring an account.

---

## Metrics

Every 429 response increments the `aurynix_rate_limit_rejections_total` Prometheus counter, labeled by `group`. See [Observability](observability.md) for details.

---

## Testing Rate Limits

```bash
# Hit the chat endpoint 25 times rapidly
for i in $(seq 1 25); do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -X POST http://localhost:8000/api/v1/chat/stream \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"message":"test"}'
done
# First 20 → 200, remaining → 429
```
