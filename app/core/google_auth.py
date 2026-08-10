"""Google OAuth 2.0 helpers — build flow, exchange code, restore credentials."""
import asyncio
import json
from typing import Any

from app.core.config import settings
from app.core.crypto import decrypt, encrypt


_GOOGLE_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
_GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"

GOOGLE_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]


def _client_config() -> dict[str, Any]:
    return {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uris": [settings.google_redirect_uri],
            "auth_uri": _GOOGLE_AUTH_URI,
            "token_uri": _GOOGLE_TOKEN_URI,
        }
    }


def _build_flow():
    from google_auth_oauthlib.flow import Flow

    flow = Flow.from_client_config(_client_config(), scopes=GOOGLE_SCOPES)
    flow.redirect_uri = settings.google_redirect_uri
    return flow


def get_authorization_url() -> tuple[str, str]:
    """Return (auth_url, state). Call from asyncio.to_thread if needed."""
    flow = _build_flow()
    url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return url, state


async def exchange_code_async(code: str, state: str) -> dict[str, Any]:
    """Exchange an authorization code for tokens (runs sync client in thread)."""

    def _exchange() -> dict[str, Any]:
        flow = _build_flow()
        flow.fetch_token(code=code)
        creds = flow.credentials
        return {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": list(creds.scopes or []),
        }

    return await asyncio.to_thread(_exchange)


def token_dict_to_encrypted(token_dict: dict[str, Any]) -> str:
    return encrypt(json.dumps(token_dict))


def encrypted_to_credentials(encrypted: str):
    """Return a google.oauth2.credentials.Credentials from an encrypted blob."""
    from google.oauth2.credentials import Credentials

    d = json.loads(decrypt(encrypted))
    return Credentials(
        token=d["token"],
        refresh_token=d.get("refresh_token"),
        token_uri=d["token_uri"],
        client_id=d["client_id"],
        client_secret=d["client_secret"],
        scopes=d.get("scopes"),
    )
