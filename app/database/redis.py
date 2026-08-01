from redis.asyncio import Redis, from_url

from app.core.config import settings

_redis_pool: Redis | None = None


async def get_redis() -> Redis:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=20,
        )
    return _redis_pool


async def close_redis() -> None:
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.aclose()
        _redis_pool = None


async def check_redis_health() -> bool:
    try:
        r = await get_redis()
        return await r.ping()
    except Exception:
        return False
