import uuid

from fastapi import APIRouter, File, UploadFile

from app.core.dependencies import CurrentUser, DbSession, RedisClient
from app.schemas.document import DocumentListResponse, DocumentResponse
from app.services import document as doc_service

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", response_model=DocumentResponse, status_code=202)
async def upload_document(
    current_user: CurrentUser,
    db: DbSession,
    file: UploadFile = File(...),
) -> DocumentResponse:
    return await doc_service.upload_document(file, current_user, db)


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    current_user: CurrentUser,
    db: DbSession,
) -> DocumentListResponse:
    return await doc_service.list_documents(current_user, db)


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> DocumentResponse:
    return await doc_service.get_document(document_id, current_user, db)


@router.get("/{document_id}/chunks")
async def get_document_chunks(
    document_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> list[dict]:
    """Return the raw text chunks stored in Qdrant for a document."""
    from app.core.config import settings
    from app.database.qdrant import get_qdrant_client
    from qdrant_client.http.models import FieldCondition, Filter, MatchValue

    # Verify the document belongs to the user
    await doc_service.get_document(document_id, current_user, db)

    client = await get_qdrant_client()
    points, _ = await client.scroll(
        collection_name=settings.qdrant_collection,
        scroll_filter=Filter(
            must=[
                FieldCondition(key="doc_id", match=MatchValue(value=str(document_id))),
                FieldCondition(key="user_id", match=MatchValue(value=str(current_user.id))),
            ]
        ),
        with_payload=True,
        limit=200,
    )

    chunks = [
        {
            "index": i + 1,
            "page": (p.payload or {}).get("page"),
            "content": (p.payload or {}).get("page_content", ""),
        }
        for i, p in enumerate(
            sorted(points, key=lambda p: (p.payload or {}).get("page") or 0)
        )
    ]
    return chunks


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> None:
    await doc_service.delete_document(document_id, current_user, db)


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str, current_user: CurrentUser, redis: RedisClient) -> dict:
    """Return the status of a background ingest job by ARQ job ID."""
    try:
        from arq import create_pool
        from arq.connections import RedisSettings
        from arq.jobs import Job, JobStatus

        from app.core.config import settings

        pool = await create_pool(
            RedisSettings(
                host=settings.redis_host,
                port=settings.redis_port,
                password=settings.redis_password or None,
            )
        )
        job = Job(job_id=job_id, redis=pool)
        status = await job.status()
        result = None
        if status == JobStatus.complete:
            try:
                result = await job.result(timeout=0)
            except Exception:
                pass
        await pool.aclose()
        return {"job_id": job_id, "status": status.value, "result": result}
    except Exception as exc:
        return {"job_id": job_id, "status": "error", "detail": str(exc)}
