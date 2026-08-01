import uuid
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError
from app.core.security import decode_token
from app.database.postgres import get_async_session
from app.database.redis import get_redis
from app.models.user import User

_bearer = HTTPBearer(auto_error=True)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> User:
    token = credentials.credentials
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise AuthenticationError("Invalid or expired token.").to_http_exception()

    jti = payload.get("jti", "")
    if await redis.get(f"blacklist:{jti}"):
        raise AuthenticationError("Token has been revoked.").to_http_exception()

    user_id_str = payload.get("sub")
    try:
        user_id = uuid.UUID(user_id_str)
    except (TypeError, ValueError):
        raise AuthenticationError("Invalid token subject.").to_http_exception()

    result = await db.execute(select(User).where(User.id == user_id, User.is_active.is_(True)))
    user = result.scalar_one_or_none()
    if not user:
        raise AuthenticationError("User not found or inactive.").to_http_exception()

    return user


# Convenience type alias used in router signatures
CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[AsyncSession, Depends(get_async_session)]
RedisClient = Annotated[Redis, Depends(get_redis)]
