from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_checkpointer: AsyncPostgresSaver | None = None
_pool: AsyncConnectionPool | None = None


async def get_checkpointer() -> AsyncPostgresSaver:
    global _checkpointer, _pool
    if _checkpointer is None:
        conninfo = settings.checkpointer_database_url
        _pool = AsyncConnectionPool(
            conninfo=conninfo,
            max_size=5,
            kwargs={
                "autocommit": True,
                "prepare_threshold": 0,
                "keepalives": 1,
                "keepalives_idle": 30,
                "keepalives_interval": 5,
                "keepalives_count": 5,
            },
            check=AsyncConnectionPool.check_connection,
            reconnect_attempts=5,
            open=False,
        )
        await _pool.open()
        _checkpointer = AsyncPostgresSaver(_pool)
        await _checkpointer.setup()
        logger.info("LangGraph checkpointer initialized")
    return _checkpointer


async def close_checkpointer() -> None:
    global _checkpointer, _pool
    _checkpointer = None
    if _pool is not None:
        await _pool.close()
        _pool = None
