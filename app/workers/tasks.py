"""ARQ worker task definitions."""
import uuid
from pathlib import Path

from arq import ArqRedis

from app.core.logging import get_logger

logger = get_logger(__name__)


async def ingest_document(
    ctx: dict,
    *,
    file_path: str,
    doc_id: str,
    user_id: str,
    db_url: str,
) -> dict:
    """Ingest a document into the vector store and update its DB status."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.document import Document
    from app.rag.pipeline import RAGPipeline

    engine = create_async_engine(db_url)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    try:
        pipeline = RAGPipeline()
        chunk_count = await pipeline.ingest(Path(file_path), doc_id=doc_id, user_id=user_id)
        status, error = "ready", None
        logger.info("Document ingested", doc_id=doc_id, chunks=chunk_count)
    except Exception as exc:
        chunk_count, status, error = 0, "failed", str(exc)
        logger.error("Document ingestion failed", doc_id=doc_id, error=error)

    async with session_factory() as session:
        result = await session.execute(select(Document).where(Document.id == uuid.UUID(doc_id)))
        doc = result.scalar_one_or_none()
        if doc:
            doc.status = status
            doc.chunk_count = chunk_count if status == "ready" else None
            doc.error_message = error
            await session.commit()

    await engine.dispose()
    return {"doc_id": doc_id, "status": status, "chunk_count": chunk_count}
