# Authentication

Aurynix uses **JWT (JSON Web Tokens)** for stateless authentication, with **Redis** for token revocation.

---

## Token types

| Type | Lifetime | Purpose |
|---|---|---|
| Access token | 60 minutes (configurable) | Authenticate API requests |
| Refresh token | 30 days (configurable) | Obtain new access tokens without re-login |

Both tokens are signed with `HS256` using `SECRET_KEY`.

---

## Token payload

```json
{
    "sub": "<user_id>",
    "jti": "<uuid>",
    "type": "access",
    "iat": 1785623134,
    "exp": 1785626734
}
```

- `sub` — user UUID
- `jti` — unique token ID used for revocation
- `type` — `"access"` or `"refresh"`

---

## Auth flow

### Register / Login

```
POST /auth/register   →   access_token + refresh_token
POST /auth/login      →   access_token + refresh_token
```

### Authenticated request

```
GET /auth/me
Authorization: Bearer <access_token>
    │
    ▼
decode JWT → check expiry → check Redis blacklist → load user from DB
```

### Refresh

```
POST /auth/refresh
{"refresh_token": "eyJ..."}
    │
    ▼
validate refresh token → blacklist old JTI → issue new access + refresh tokens
```

### Logout

```
POST /auth/logout
Authorization: Bearer <access_token>
    │
    ▼
extract JTI → store in Redis with TTL = remaining token lifetime
```

---

## Token revocation (Redis blacklist)

On logout, the token's JTI is written to Redis:

```
KEY:   blacklist:<jti>
VALUE: "1"
TTL:   remaining seconds until token expiry
```

Every authenticated request checks `redis.get(f"blacklist:{jti}")`. If the key exists, the request is rejected with `401`.

The TTL ensures Redis does not accumulate stale keys — entries expire automatically when the token would have expired anyway.

---

## Password hashing

Passwords are hashed with **bcrypt** (work factor 12) using the `bcrypt` library directly:

```python
hash_password(plain: str) -> str      # bcrypt.hashpw(plain.encode(), bcrypt.gensalt())
verify_password(plain: str, hashed: str) -> bool  # bcrypt.checkpw(...)
```

`passlib` is not used — it is incompatible with `bcrypt>=4.0`.

---

## FastAPI dependency injection

```python
# In any route that requires authentication:
async def my_route(current_user: CurrentUser, ...) -> ...:
    ...

# CurrentUser is a type alias defined in app/core/dependencies.py:
CurrentUser = Annotated[User, Depends(get_current_user)]
```

`get_current_user`:
1. Extracts Bearer token from `Authorization` header
2. Decodes and validates JWT
3. Checks Redis blacklist
4. Loads `User` from PostgreSQL
5. Returns the `User` ORM object (or raises `401`)

---

## Security notes

- `SECRET_KEY` must be at least 32 random bytes. Generate with: `openssl rand -hex 32`
- Rotate `SECRET_KEY` to invalidate all existing tokens (e.g. after a breach)
- Access tokens are short-lived (60 min) to limit exposure if intercepted
- Refresh token rotation: each refresh invalidates the previous refresh token
- HTTPS is required in production — tokens in transit are otherwise exposed
