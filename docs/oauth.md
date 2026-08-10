# OAuth 2.0 — Google Integration

Gmail and Google Calendar require per-user OAuth 2.0 tokens. Each user connects their Google account and Aurynix stores the resulting token set, AES-256-GCM encrypted, in the `oauth_tokens` table.

---

## Setup — Google Cloud Console

1. Go to [console.cloud.google.com](https://console.cloud.google.com).
2. Create a project (or reuse one).
3. **APIs & Services → Enable APIs:** Gmail API and Google Calendar API.
4. **APIs & Services → OAuth consent screen:**
   - User type: External (for testing) or Internal (Workspace).
   - Add scopes: `openid`, `email`, `gmail.readonly`, `gmail.send`, `calendar.readonly`, `calendar.events`.
5. **APIs & Services → Credentials → Create OAuth 2.0 Client ID:**
   - Application type: **Web application**.
   - Authorized redirect URI: `http://localhost:8000/api/v1/oauth/google/callback`
6. Copy **Client ID** and **Client Secret** into `.env`.

```bash
GOOGLE_CLIENT_ID=123456789-abc.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-...
GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/oauth/google/callback
OAUTH_SUCCESS_REDIRECT=http://localhost:3000/settings?oauth=success
```

---

## OAuth Flow

```
User clicks "Connect Google"
        │
GET /api/v1/oauth/google/authorize   (requires JWT)
        │
        ▼
Aurynix generates state → stored in Redis (10-min TTL)
Returns { "url": "https://accounts.google.com/...", "state": "..." }
        │
        ▼
Frontend redirects browser to Google consent screen
        │
User grants permission
        │
        ▼
GET /api/v1/oauth/google/callback?code=...&state=...
        │
Aurynix validates state via Redis lookup → retrieves user_id
Exchanges code for access + refresh tokens
Stores encrypted token row in oauth_tokens table
        │
        ▼
302 → OAUTH_SUCCESS_REDIRECT (frontend)
```

**State parameter:** A random string generated per authorization attempt. It is stored in Redis keyed as `oauth:state:{state}` with the user's UUID as the value and a 10-minute TTL. This prevents CSRF without needing a separate session store.

---

## Token Storage

**Model: `OAuthToken`** (`app/models/oauth_token.py`)

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key |
| `user_id` | UUID FK → `users.id` | CASCADE delete |
| `provider` | `varchar(50)` | `"google"` |
| `encrypted_token` | `text` | AES-256-GCM encrypted JSON blob |
| `scopes` | `text` | Space-separated list of granted scopes |
| `created_at` | `timestamptz` | |
| `updated_at` | `timestamptz` | |

One row per user per provider. Upserted on reconnect (`encrypted_token` and `scopes` are overwritten).

### Encryption (`app/core/crypto.py`)

```python
def encrypt(plaintext: str) -> str:
    """Return base64url-encoded nonce + ciphertext."""
    nonce = os.urandom(12)
    ciphertext = AESGCM(_derive_key()).encrypt(nonce, plaintext.encode(), None)
    return base64.urlsafe_b64encode(nonce + ciphertext).decode()

def decrypt(blob: str) -> str:
    raw = base64.urlsafe_b64decode(blob.encode())
    nonce, ciphertext = raw[:12], raw[12:]
    return AESGCM(_derive_key()).decrypt(nonce, ciphertext, None).decode()
```

Key is derived via `hashlib.sha256(settings.secret_key.encode()).digest()`. Rotating `SECRET_KEY` invalidates all stored tokens — users must reconnect.

The encrypted blob is a JSON object:
```json
{
  "token": "<access_token>",
  "refresh_token": "<refresh_token>",
  "token_uri": "https://oauth2.googleapis.com/token",
  "client_id": "...",
  "client_secret": "...",
  "scopes": ["openid", "https://www.googleapis.com/auth/gmail.readonly", ...]
}
```

### Restoring credentials

```python
# app/core/google_auth.py
def encrypted_to_credentials(encrypted: str) -> google.oauth2.credentials.Credentials:
    d = json.loads(decrypt(encrypted))
    return Credentials(
        token=d["token"],
        refresh_token=d.get("refresh_token"),
        token_uri=d["token_uri"],
        client_id=d["client_id"],
        client_secret=d["client_secret"],
        scopes=d.get("scopes"),
    )
```

The Google SDK handles access token refresh automatically when the credentials are used.

---

## API Endpoints

### `GET /api/v1/oauth/google/authorize`

**Auth required.** Generates an authorization URL and stores the state in Redis.

**Response:**
```json
{
  "url": "https://accounts.google.com/o/oauth2/auth?...",
  "state": "abc123xyz"
}
```

### `GET /api/v1/oauth/google/callback`

**No auth.** Handles Google's redirect after user consent.

Query params: `code`, `state` (or `error` on denial).

Validates state via Redis, exchanges code for tokens, upserts `OAuthToken` row, then redirects to `OAUTH_SUCCESS_REDIRECT`.

### `GET /api/v1/oauth/google/status`

**Auth required.** Returns connection status for the current user.

**Response (connected):**
```json
{ "connected": true, "scopes": ["openid", "https://...gmail.readonly", ...] }
```

**Response (not connected):**
```json
{ "connected": false, "scopes": [] }
```

### `DELETE /api/v1/oauth/google/disconnect`

**Auth required.** Deletes the `OAuthToken` row. Does **not** revoke the token at Google (so the user must also revoke at myaccount.google.com/permissions if needed).

**Response:** `204 No Content`

---

## Security Notes

- The state value is a random string (not a JWT) stored in Redis with a 10-minute TTL.
- Tokens are never logged. The encrypted blob is treated as an opaque string throughout the codebase.
- Rotating `SECRET_KEY` invalidates all stored tokens.
- Gmail and Calendar tools check for a valid `OAuthToken` row before making any API call, and return a human-readable error if the user hasn't connected their Google account.
