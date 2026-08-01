"""
LangGraph conversation-history checkpointer backed by PostgreSQL.

Uses langgraph-checkpoint-postgres AsyncPostgresSaver which requires a
psycopg3 connection string (no driver prefix — just 'postgresql://').
"""
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_checkpointer: AsyncPostgresSaver | None = None


async def get_checkpointer() -> AsyncPostgresSaver:
    global _checkpointer
    if _checkpointer is None:
        _checkpointer = AsyncPostgresSaver.from_conn_string(
            settings.checkpointer_database_url
        )
        await _checkpointer.setup()
        logger.info("LangGraph checkpointer initialized")
    return _checkpointer


async def close_checkpointer() -> None:
    global _checkpointer
    if _checkpointer is not None:
        await _checkpointer.conn.close()
        _checkpointer = None
