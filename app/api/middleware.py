import time
import uuid

import structlog
from fastapi import Request
from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

from app.core.config import settings


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


def _rate_limit_group(path: str) -> str:
    if "/chat" in path:
        return "chat"
    if "/auth" in path:
        return "auth"
    if "/documents" in path:
        return "documents"
    return "default"


def _rate_limit_for_group(group: str) -> int:
    return {
        "chat": settings.rate_limit_chat,
        "auth": settings.rate_limit_auth,
        "documents": settings.rate_limit_documents,
        "default": settings.rate_limit_default,
    }[group]


def _extract_user_id(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[len("Bearer ") :]
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        return payload.get("sub")
    except JWTError:
        return None


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        from app.database.redis import get_redis

        path = request.url.path
        if not path.startswith("/api/v1/"):
            return await call_next(request)

        user_id = _extract_user_id(request)
        scope = user_id if user_id else f"ip:{request.client.host if request.client else 'unknown'}"

        group = _rate_limit_group(path)
        limit = _rate_limit_for_group(group)
        window = int(time.time() // 60)
        key = f"ratelimit:{scope}:{group}:{window}"

        try:
            redis = await get_redis()
            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, 90)
        except Exception:
            # Redis unavailable — fail open rather than blocking all requests
            return await call_next(request)

        remaining = max(0, limit - count)
        reset_ts = (window + 1) * 60

        if count > limit:
            from app.core.metrics import rate_limit_rejections_total

            rate_limit_rejections_total.labels(group=group).inc()
            retry_after = reset_ts - int(time.time())
            return JSONResponse(
                {"detail": f"Rate limit exceeded. Retry after {retry_after}s."},
                status_code=429,
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_ts),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_ts)
        return response
