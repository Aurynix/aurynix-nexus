import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class MemoryFactCreate(BaseModel):
    key: str
    value: str
    source: Literal["manual", "auto"] = "manual"
    confidence: float = 1.0


class MemoryFactUpdate(BaseModel):
    key: str | None = None
    value: str | None = None
    confidence: float | None = None


class MemoryFactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key: str
    value: str
    source: str
    confidence: float
    created_at: datetime
    updated_at: datetime
