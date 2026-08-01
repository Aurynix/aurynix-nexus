from fastapi import APIRouter
from pydantic import BaseModel

from app.database.postgres import check_postgres_health
from app.database.qdrant import check_qdrant_health
from app.database.redis import check_redis_health

router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    status: str


class ReadinessResponse(BaseModel):
    status: str
    checks: dict[str, str]


@router.get("", response_model=HealthResponse)
async def liveness() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/ready", response_model=ReadinessResponse)
async def readiness() -> ReadinessResponse:
    checks = {
        "postgres": "ok" if await check_postgres_health() else "error",
        "redis": "ok" if await check_redis_health() else "error",
        "qdrant": "ok" if await check_qdrant_health() else "error",
    }
    status = "ready" if all(v == "ok" for v in checks.values()) else "degraded"
    return ReadinessResponse(status=status, checks=checks)
