# OAuth 2.0 — Google Integration

Gmail and Google Calendar require per-user OAuth 2.0 tokens. Each user connects their own Google account and Aurynix stores the resulting access/refresh token pair, encrypted at rest.

---

## Setup — Google Cloud Console

1. Go to [console.cloud.google.com](https://console.cloud.google.com).
2. Create a project (or reuse one).
3. **APIs & Services → Enable APIs:**
   - Gmail API
   - Google Calendar API
4. **APIs & Services → OAuth consent screen:**
   - User type: External (for testing) or Internal (Workspace only).
   - Add scopes:
     - `https://www.googleapis.com/auth/gmail.modify`
     - `https://www.googleapis.com/auth/calendar`
     - `openid`, `email`, `profile`
5. **APIs & Services → Credentials → Create OAuth 2.0 Client ID:**
   - Application type: Web application.
   - Authorized redirect URI: `http://localhost:8000/api/v1/oauth/google/callback`
6. Copy **Client ID** and **Client Secret** into `.env`.

```bash
GOOGLE_CLIENT_ID=123456789-abc.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-...
GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/oauth/google/callback
```

---

## OAuth Flow

```
User clicks "Connect Google"
        │
GET /api/v1/oauth/google/authorize
        │
        ▼
Aurynix builds authorization URL (state = JWT-signed user_id)
        │
        ▼
Browser → accounts.google.com/o/oauth2/auth
        │
User grants permission
        │
        ▼
GET /api/v1/oauth/google/callback?code=...&state=...
        │
Aurynix verifies state, exchanges code for tokens
        │
        ▼
OAuthToken row created/updated (encrypted in DB)
        │
        ▼
Redirect → frontend success page
```

### Why `state` carries a signed JWT?

The `state` parameter is a short-lived JWT signed with `SECRET_KEY`. It encodes the user's ID so the callback handler knows which user just completed the OAuth flow without a server-side session. It expires in 10 minutes.

---

## Token Storage

**Model: `OAuthToken`** (`app/models/oauth_token.py`)

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key |
| `user_id` | UUID FK | One row per provider per user |
| `provider` | `varchar(20)` | `"google"` |
| `access_token` | `text` | AES-256-GCM encrypted |
| `refresh_token` | `text` | AES-256-GCM encrypted |
| `token_expiry` | `timestamptz` | When the access token expires |
| `scopes` | `text[]` | Granted scopes |
| `created_at` | `timestamptz` | |
| `updated_at` | `timestamptz` | |

Tokens are encrypted using a key derived from `SECRET_KEY` via HKDF. The raw token never touches the database.

```python
# app/core/crypto.py
def encrypt_token(plain: str) -> str:
    key = derive_key(settings.secret_key)
    nonce = os.urandom(12)
    ct = AESGCM(key).encrypt(nonce, plain.encode(), None)
    return base64.b64encode(nonce + ct).decode()

def decrypt_token(cipher: str) -> str:
    raw = base64.b64decode(cipher)
    nonce, ct = raw[:12], raw[12:]
    key = derive_key(settings.secret_key)
    return AESGCM(key).decrypt(nonce, ct, None).decode()
```

---

## Token Refresh

Google access tokens expire after 1 hour. The `get_google_credentials()` helper handles refresh transparently:

```python
# app/core/google_auth.py
async def get_google_credentials(user_id: str, db: AsyncSession) -> Credentials:
    token = await load_oauth_token(user_id, "google", db)
    if not token:
        raise OAuthNotConnectedError("Google account not connected.")

    creds = Credentials(
        token=decrypt_token(token.access_token),
        refresh_token=decrypt_token(token.refresh_token),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
    )

    if creds.expired:
        creds.refresh(Request())
        # persist updated access token
        await update_oauth_token(user_id, creds, db)

    return creds
```

This is called by both the Gmail tool and the Calendar tool before any API request.

---

## API Endpoints

### `GET /api/v1/oauth/google/authorize`

Returns a redirect URL. The client should navigate the user there.

**Response:**
```json
{
  "authorization_url": "https://accounts.google.com/o/oauth2/auth?..."
}
```

### `GET /api/v1/oauth/google/callback`

Handles Google's redirect. Not called directly by the frontend.

Stores the token and redirects to `OAUTH_SUCCESS_REDIRECT` (configurable).

### `GET /api/v1/oauth/google/status`

Returns connection status for the current user.

**Response (connected):**
```json
{
  "connected": true,
  "provider": "google",
  "scopes": ["gmail.modify", "calendar", "openid"],
  "connected_at": "2026-08-01T10:00:00Z"
}
```

**Response (not connected):**
```json
{ "connected": false }
```

### `DELETE /api/v1/oauth/google/revoke`

Revokes the token at Google and deletes the `OAuthToken` row.

**Response:** `204 No Content`

---

## Security Notes

- The `state` JWT uses `HS256` and expires in 10 minutes — replay attacks outside that window are rejected.
- Tokens are never logged. Structured log fields that might contain a token are always redacted.
- The encryption key is derived via HKDF from `SECRET_KEY` — rotating `SECRET_KEY` invalidates all stored tokens (users must reconnect).
- Scopes are stored and checked at tool call time — if a required scope is missing, the tool raises `OAuthScopeError` instead of silently failing.
