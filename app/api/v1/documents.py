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
