"""Google OAuth 2.0 endpoints."""
import asyncio
import uuid

from fastapi import APIRouter
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.dependencies import CurrentUser, DbSession, RedisClient
from app.core.google_auth import (
    GOOGLE_SCOPES,
    exchange_code_async,
    get_authorization_url,
    token_dict_to_encrypted,
)
from app.models.oauth_token import OAuthToken

router = APIRouter(prefix="/oauth", tags=["oauth"])

_STATE_TTL = 600  # 10 minutes


@router.get("/google/authorize")
async def google_authorize(current_user: CurrentUser, redis: RedisClient) -> dict:
    """Return a Google OAuth authorization URL for the current user."""
    auth_url, state = await asyncio.to_thread(get_authorization_url)
    await redis.setex(f"oauth:state:{state}", _STATE_TTL, str(current_user.id))
    return {"url": auth_url, "state": state}


def _error_redirect(reason: str) -> RedirectResponse:
    base = settings.oauth_success_redirect.replace("success", "error")
    return RedirectResponse(url=f"{base}?reason={reason}")


@router.get("/google/callback")
async def google_callback(
    db: DbSession,
    redis: RedisClient,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    """Handle the redirect from Google after the user grants access."""
    if error:
        return _error_redirect(error)
    if not code or not state:
        return _error_redirect("missing_params")

    user_id_raw = await redis.get(f"oauth:state:{state}")
    if not user_id_raw:
        return _error_redirect("invalid_state")
    await redis.delete(f"oauth:state:{state}")

    user_id = uuid.UUID(
        user_id_raw if isinstance(user_id_raw, str) else user_id_raw.decode()
    )

    token_dict = await exchange_code_async(code, state)
    encrypted = token_dict_to_encrypted(token_dict)
    scopes = " ".join(token_dict.get("scopes") or GOOGLE_SCOPES)

    result = await db.execute(
        select(OAuthToken).where(
            OAuthToken.user_id == user_id, OAuthToken.provider == "google"
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.encrypted_token = encrypted
        existing.scopes = scopes
    else:
        db.add(
            OAuthToken(
                user_id=user_id, provider="google", encrypted_token=encrypted, scopes=scopes
            )
        )

    await db.commit()
    return RedirectResponse(url=settings.oauth_success_redirect)


@router.get("/google/status")
async def google_status(current_user: CurrentUser, db: DbSession) -> dict:
    """Return whether the current user has connected their Google account."""
    result = await db.execute(
        select(OAuthToken).where(
            OAuthToken.user_id == current_user.id, OAuthToken.provider == "google"
        )
    )
    token = result.scalar_one_or_none()
    if not token:
        return {"connected": False, "scopes": []}
    return {"connected": True, "scopes": token.scopes.split()}


@router.delete("/google/disconnect", status_code=204)
async def google_disconnect(current_user: CurrentUser, db: DbSession) -> None:
    """Remove the Google OAuth token for the current user."""
    await db.execute(
        delete(OAuthToken).where(
            OAuthToken.user_id == current_user.id, OAuthToken.provider == "google"
        )
    )
    await db.commit()
