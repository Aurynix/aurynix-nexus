import psycopg
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_checkpointer: AsyncPostgresSaver | None = None
_conn: psycopg.AsyncConnection | None = None


async def get_checkpointer() -> AsyncPostgresSaver:
    global _checkpointer, _conn
    if _checkpointer is None:
        # Use a single direct connection rather than a pool.
        # Neon's pooler URL (contains -pooler) uses PgBouncer; layering our
        # own AsyncConnectionPool on top causes SSL drops mid-stream.
        conninfo = settings.checkpointer_database_url
        _conn = await psycopg.AsyncConnection.connect(
            conninfo,
            autocommit=True,
            prepare_threshold=0,
            keepalives=1,
            keepalives_idle=30,
            keepalives_interval=5,
            keepalives_count=5,
        )
        _checkpointer = AsyncPostgresSaver(_conn)
        await _checkpointer.setup()
        logger.info("LangGraph checkpointer initialized")
    return _checkpointer


async def close_checkpointer() -> None:
    global _checkpointer, _conn
    _checkpointer = None
    if _conn is not None:
        await _conn.close()
        _conn = None
