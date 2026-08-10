# Rate Limiting

Aurynix enforces per-user rate limits using a Redis sliding-window counter. Limits are applied at the middleware layer before any business logic runs.

---

## How It Works

Each authenticated request increments a Redis key scoped to `user_id + endpoint_group`. If the count exceeds the limit within the window, the request is rejected immediately with `429 Too Many Requests`.

```
Request arrives
      │
Extract user_id from JWT
      │
      ▼
INCR  ratelimit:{user_id}:{group}:{window}
      │
EXPIRE key to window_seconds (if new key)
      │
      ▼
count > limit?
  ├── No  → pass through to handler
  └── Yes → 429 { "detail": "Rate limit exceeded. Retry after N seconds." }
```

### Redis key structure

```
ratelimit:550e8400-e29b...:chat:1754042340
          └──────────────┘ └──┘ └────────┘
               user_id     group  window
                                 (Unix minute)
```

The window is the current Unix timestamp floored to the nearest minute — a new counter starts each minute automatically.

---

## Limits by Endpoint Group

| Group | Endpoints | Default limit | Burst |
|---|---|---|---|
| `chat` | `/api/v1/chat/stream` | 20 req/min | — |
| `auth` | `/api/v1/auth/login`, `/register` | 10 req/min | — |
| `documents` | `/api/v1/documents/*` | 30 req/min | — |
| `memory` | `/api/v1/memory/*` | 60 req/min | — |
| `default` | All other authenticated endpoints | 60 req/min | — |

All limits are configurable via environment variables:

```bash
RATE_LIMIT_CHAT=20
RATE_LIMIT_AUTH=10
RATE_LIMIT_DOCUMENTS=30
RATE_LIMIT_MEMORY=60
RATE_LIMIT_DEFAULT=60
```

---

## Implementation

### Middleware

```python
# app/api/middleware.py (addition)
class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        user_id = extract_user_id(request)   # from JWT, or None
        if user_id is None:
            return await call_next(request)  # unauthenticated reqs: no limit here

        group = resolve_group(request.url.path)
        limit = settings.rate_limits[group]
        window = int(time.time() // 60)
        key = f"ratelimit:{user_id}:{group}:{window}"

        redis = get_redis()
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, 90)  # 90s TTL — covers the minute boundary

        if count > limit:
            retry_after = 60 - (int(time.time()) % 60)
            return JSONResponse(
                {"detail": f"Rate limit exceeded. Retry after {retry_after}s."},
                status_code=429,
                headers={"Retry-After": str(retry_after)},
            )

        return await call_next(request)
```

### Response headers

Every rate-limited response includes:

```
X-RateLimit-Limit: 20
X-RateLimit-Remaining: 17
X-RateLimit-Reset: 1754042400
Retry-After: 23          ← only on 429
```

---

## Unauthenticated Endpoints

Login and register are rate-limited by IP address instead of user ID (since no token is available):

```
ratelimit:ip:192.168.1.1:auth:1754042340
```

IP-based limits are stricter to prevent credential stuffing.

---

## Bypassing Limits (Admin)

Requests carrying an `X-Admin-Token` header (matching `ADMIN_TOKEN` env var) bypass rate limiting entirely. This is intended for internal health checks and admin scripts, not for general use.

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
