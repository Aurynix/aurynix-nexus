from datetime import UTC, datetime, timedelta
from uuid import uuid4

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


def _create_token(
    user_id: str,
    token_type: str,
    expire_delta: timedelta,
) -> tuple[str, str]:
    jti = str(uuid4())
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "jti": jti,
        "type": token_type,
        "iat": now,
        "exp": now + expire_delta,
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)
    return token, jti


def create_access_token(user_id: str) -> tuple[str, str]:
    delta = timedelta(minutes=settings.access_token_expire_minutes)
    return _create_token(user_id, "access", delta)


def create_refresh_token(user_id: str) -> tuple[str, str]:
    delta = timedelta(days=settings.refresh_token_expire_days)
    return _create_token(user_id, "refresh", delta)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        return None
