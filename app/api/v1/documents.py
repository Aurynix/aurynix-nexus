import uuid

from fastapi import APIRouter, UploadFile, File

from app.core.dependencies import CurrentUser, DbSession
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
