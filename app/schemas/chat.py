import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class ChatRequest(BaseModel):
    message: str
    conversation_id: uuid.UUID | None = None


class SSEEvent(BaseModel):
    type: Literal[
        "metadata",
        "agent_start",
        "tool_start",
        "tool_end",
        "token",
        "interrupt",
        "error",
        "done",
        "ping",
    ]
    data: dict[str, Any] | None = None

    def to_sse(self) -> str:
        import json

        payload: dict[str, Any] = {"type": self.type}
        if self.data:
            payload.update(self.data)
        return f"data: {json.dumps(payload)}\n\n"


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: str
    content: str
    created_at: datetime


class ConversationDetailResponse(ConversationResponse):
    messages: list[MessageResponse] = []
