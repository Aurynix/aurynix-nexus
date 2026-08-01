from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError, ConflictError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import TokenResponse


async def register(email: str, password: str, db: AsyncSession) -> TokenResponse:
    result = await db.execute(select(User).where(User.email == email))
    if result.scalar_one_or_none():
        raise ConflictError("Email already registered.").to_http_exception()

    user = User(email=email, hashed_password=hash_password(password))
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return _issue_tokens(str(user.id))


async def login(email: str, password: str, db: AsyncSession) -> TokenResponse:
    result = await db.execute(select(User).where(User.email == email, User.is_active.is_(True)))
    user = result.scalar_one_or_none()
    if not user or not verify_password(password, user.hashed_password):
        raise AuthenticationError("Invalid credentials.").to_http_exception()

    return _issue_tokens(str(user.id))


async def refresh_tokens(refresh_token: str, redis: Redis) -> TokenResponse:
    payload = decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise AuthenticationError("Invalid refresh token.").to_http_exception()

    jti = payload.get("jti", "")
    if await redis.get(f"blacklist:{jti}"):
        raise AuthenticationError("Refresh token has been revoked.").to_http_exception()

    await _blacklist_jti(jti, payload, redis)
    return _issue_tokens(payload["sub"])


async def logout(access_token_payload: dict, redis: Redis) -> None:
    jti = access_token_payload.get("jti", "")
    await _blacklist_jti(jti, access_token_payload, redis)


def _issue_tokens(user_id: str) -> TokenResponse:
    access_token, _ = create_access_token(user_id)
    refresh_token, _ = create_refresh_token(user_id)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


async def _blacklist_jti(jti: str, payload: dict, redis: Redis) -> None:
    exp = payload.get("exp", 0)
    now = int(datetime.now(UTC).timestamp())
    ttl = max(exp - now, 1)
    await redis.setex(f"blacklist:{jti}", ttl, "1")
