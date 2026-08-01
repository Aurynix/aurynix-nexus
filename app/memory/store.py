"""
LangGraph long-term memory store backed by PostgreSQL.

Facts are stored under namespace ("users", <user_id>, "facts") and keyed
by fact key. Each item's value is {"key": str, "value": str, "confidence": float}.
"""
from langgraph.store.postgres import AsyncPostgresStore

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_store: AsyncPostgresStore | None = None


async def get_memory_store() -> AsyncPostgresStore:
    global _store
    if _store is None:
        _store = AsyncPostgresStore.from_conn_string(settings.checkpointer_database_url)
        await _store.setup()
        logger.info("LangGraph memory store initialized")
    return _store


async def close_memory_store() -> None:
    global _store
    if _store is not None:
        await _store.conn.close()
        _store = None


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
