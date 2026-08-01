from langgraph.store.postgres import AsyncPostgresStore
from psycopg_pool import AsyncConnectionPool

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_store: AsyncPostgresStore | None = None
_pool: AsyncConnectionPool | None = None


async def get_memory_store() -> AsyncPostgresStore:
    global _store, _pool
    if _store is None:
        _pool = AsyncConnectionPool(
            conninfo=settings.checkpointer_database_url,
            max_size=5,
            kwargs={"autocommit": True, "prepare_threshold": 0},
            open=False,
        )
        await _pool.open()
        _store = AsyncPostgresStore(_pool)
        await _store.setup()
        logger.info("LangGraph memory store initialized")
    return _store


async def close_memory_store() -> None:
    global _store, _pool
    _store = None
    if _pool is not None:
        await _pool.close()
        _pool = None


async def load_user_facts(user_id: str, store: AsyncPostgresStore) -> list[str]:
    namespace = ("users", user_id, "facts")
    items = await store.asearch(namespace)
    facts = []
    for item in items:
        v = item.value
        facts.append(f"{v.get('key', '')}: {v.get('value', '')}")
    return facts


async def upsert_user_fact(
    user_id: str,
    key: str,
    value: str,
    confidence: float,
    store: AsyncPostgresStore,
) -> None:
    namespace = ("users", user_id, "facts")
    await store.aput(namespace, key, {"key": key, "value": value, "confidence": confidence})
