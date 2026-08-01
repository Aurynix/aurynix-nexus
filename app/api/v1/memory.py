import uuid

from fastapi import APIRouter

from app.core.dependencies import CurrentUser, DbSession
from app.schemas.memory import MemoryFactCreate, MemoryFactResponse, MemoryFactUpdate
from app.services import memory as memory_service

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("", response_model=list[MemoryFactResponse])
async def list_facts(current_user: CurrentUser, db: DbSession) -> list[MemoryFactResponse]:
    return await memory_service.list_facts(current_user, db)


@router.post("", response_model=MemoryFactResponse, status_code=201)
async def create_fact(
    body: MemoryFactCreate, current_user: CurrentUser, db: DbSession
) -> MemoryFactResponse:
    return await memory_service.create_fact(body, current_user, db)


@router.put("/{fact_id}", response_model=MemoryFactResponse)
async def update_fact(
    fact_id: uuid.UUID,
    body: MemoryFactUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> MemoryFactResponse:
    return await memory_service.update_fact(fact_id, body, current_user, db)


@router.delete("/{fact_id}", status_code=204)
async def delete_fact(
    fact_id: uuid.UUID, current_user: CurrentUser, db: DbSession
) -> None:
    await memory_service.delete_fact(fact_id, current_user, db)
