import asyncio
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from app.core.logging import get_logger
from app.models.document import Document
from app.models.user import User
from app.rag.pipeline import RAGPipeline
from app.schemas.document import DocumentListResponse, DocumentResponse

logger = get_logger(__name__)

_ALLOWED_TYPES = {"pdf", "docx", "txt"}


async def upload_document(file: UploadFile, user: User, db: AsyncSession) -> DocumentResponse:
    if not file.filename:
        raise ValidationError("Filename is required.")

    file_ext = Path(file.filename).suffix.lstrip(".").lower()
    if file_ext not in _ALLOWED_TYPES:
        raise ValidationError(f"File type '.{file_ext}' is not supported. Use: {_ALLOWED_TYPES}")

    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > settings.max_upload_size_mb:
        raise ValidationError(f"File exceeds max size of {settings.max_upload_size_mb} MB.")

    doc_id = uuid.uuid4()
    upload_path = Path(settings.upload_dir) / str(user.id)
    upload_path.mkdir(parents=True, exist_ok=True)
    file_path = upload_path / f"{doc_id}.{file_ext}"
    file_path.write_bytes(content)

    doc = Document(
        id=doc_id,
        user_id=user.id,
        filename=file.filename,
        file_type=file_ext,
        file_size=len(content),
        status="processing",
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    asyncio.create_task(
        _ingest_background(
            file_path=file_path,
            doc_id=str(doc_id),
            user_id=str(user.id),
            db_url=settings.async_database_url,
        )
    )

    logger.info("Document upload started", doc_id=str(doc_id), filename=file.filename)
    return DocumentResponse.model_validate(doc)


async def _ingest_background(file_path: Path, doc_id: str, user_id: str, db_url: str) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(db_url)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    try:
        pipeline = RAGPipeline()
        chunk_count = await pipeline.ingest(file_path, doc_id=doc_id, user_id=user_id)
        status = "ready"
        error = None
    except Exception as exc:
        logger.error("Document ingestion failed", doc_id=doc_id, error=str(exc))
        chunk_count = 0
        status = "failed"
        error = str(exc)

    async with session_factory() as session:
        result = await session.execute(select(Document).where(Document.id == uuid.UUID(doc_id)))
        doc = result.scalar_one_or_none()
        if doc:
            doc.status = status
            doc.chunk_count = chunk_count if status == "ready" else None
            doc.error_message = error
            await session.commit()

    await engine.dispose()


async def list_documents(user: User, db: AsyncSession) -> DocumentListResponse:
    result = await db.execute(
        select(Document).where(Document.user_id == user.id).order_by(Document.created_at.desc())
    )
    docs = result.scalars().all()
    return DocumentListResponse(
        items=[DocumentResponse.model_validate(d) for d in docs],
        total=len(docs),
    )


async def get_document(doc_id: uuid.UUID, user: User, db: AsyncSession) -> DocumentResponse:
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise NotFoundError("Document not found.").to_http_exception()
    if doc.user_id != user.id:
        raise PermissionDeniedError().to_http_exception()
    return DocumentResponse.model_validate(doc)


async def delete_document(doc_id: uuid.UUID, user: User, db: AsyncSession) -> None:
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise NotFoundError("Document not found.").to_http_exception()
    if doc.user_id != user.id:
        raise PermissionDeniedError().to_http_exception()

    pipeline = RAGPipeline()
    await pipeline.delete_document(str(doc_id), str(user.id))

    file_path = Path(settings.upload_dir) / str(user.id) / f"{doc_id}.{doc.file_type}"
    if file_path.exists():
        file_path.unlink()

    await db.delete(doc)
    await db.commit()
