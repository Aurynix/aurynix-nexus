import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.models.memory import MemoryFact
from app.models.user import User
from app.schemas.memory import MemoryFactCreate, MemoryFactResponse, MemoryFactUpdate


async def list_facts(user: User, db: AsyncSession) -> list[MemoryFactResponse]:
    result = await db.execute(
        select(MemoryFact)
        .where(MemoryFact.user_id == user.id)
        .order_by(MemoryFact.created_at.desc())
    )
    facts = result.scalars().all()
    return [MemoryFactResponse.model_validate(f) for f in facts]


async def create_fact(
    data: MemoryFactCreate, user: User, db: AsyncSession
) -> MemoryFactResponse:
    fact = MemoryFact(
        user_id=user.id,
        key=data.key,
        value=data.value,
        source=data.source,
        confidence=data.confidence,
    )
    db.add(fact)
    await db.commit()
    await db.refresh(fact)
    return MemoryFactResponse.model_validate(fact)


async def update_fact(
    fact_id: uuid.UUID, data: MemoryFactUpdate, user: User, db: AsyncSession
) -> MemoryFactResponse:
    result = await db.execute(select(MemoryFact).where(MemoryFact.id == fact_id))
    fact = result.scalar_one_or_none()
    if not fact:
        raise NotFoundError("Memory fact not found.").to_http_exception()
    if fact.user_id != user.id:
        raise PermissionDeniedError().to_http_exception()

    if data.key is not None:
        fact.key = data.key
    if data.value is not None:
        fact.value = data.value
    if data.confidence is not None:
        fact.confidence = data.confidence

    await db.commit()
    await db.refresh(fact)
    return MemoryFactResponse.model_validate(fact)


async def delete_fact(fact_id: uuid.UUID, user: User, db: AsyncSession) -> None:
    result = await db.execute(select(MemoryFact).where(MemoryFact.id == fact_id))
    fact = result.scalar_one_or_none()
    if not fact:
        raise NotFoundError("Memory fact not found.").to_http_exception()
    if fact.user_id != user.id:
        raise PermissionDeniedError().to_http_exception()
    await db.delete(fact)
    await db.commit()
