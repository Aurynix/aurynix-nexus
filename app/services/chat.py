import asyncio
import json
import uuid
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

from langchain_core.messages import AIMessageChunk, HumanMessage, ToolMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.conversation import Conversation, Message
from app.models.user import User
from app.schemas.chat import SSEEvent

if TYPE_CHECKING:
    from langgraph.graph.graph import CompiledGraph

logger = get_logger(__name__)

_PING_INTERVAL = 15


async def stream_chat(
    *,
    graph: "CompiledGraph",
    user: User,
    message: str,
    conversation_id: uuid.UUID | None,
    db: AsyncSession,
) -> AsyncGenerator[str, None]:
    conv = await _get_or_create_conversation(user, conversation_id, db)
    conv_id = str(conv.id)

    user_msg = Message(
        conversation_id=conv.id,
        role="user",
        content=message,
    )
    db.add(user_msg)
    await db.commit()

    config = {
        "configurable": {
            "thread_id": conv_id,
            "user_id": str(user.id),
        }
    }

    input_state = {
        "messages": [HumanMessage(content=message)],
        "user_id": str(user.id),
        "conversation_id": conv_id,
        "user_facts": [],
        "requires_human": False,
        "human_feedback": None,
        "iteration_count": 0,
        "error": None,
    }

    yield SSEEvent(
        type="metadata",
        data={"conversation_id": conv_id},
    ).to_sse()

    assistant_content_parts: list[str] = []
    ping_task: asyncio.Task | None = None

    async def _ping_generator() -> AsyncGenerator[str, None]:
        while True:
            await asyncio.sleep(_PING_INTERVAL)
            yield SSEEvent(type="ping").to_sse()

    try:
        async for event in graph.astream_events(input_state, config=config, version="v2"):
            kind = event["event"]
            name = event.get("name", "")
            data: dict[str, Any] = event.get("data", {})

            if kind == "on_chat_model_start":
                yield SSEEvent(type="agent_start", data={"agent": name}).to_sse()

            elif kind == "on_chat_model_stream":
                chunk = data.get("chunk")
                if isinstance(chunk, AIMessageChunk) and chunk.content:
                    token = chunk.content
                    assistant_content_parts.append(token)
                    yield SSEEvent(type="token", data={"content": token}).to_sse()

            elif kind == "on_tool_start":
                yield SSEEvent(
                    type="tool_start",
                    data={"tool": name, "input": str(data.get("input", ""))},
                ).to_sse()

            elif kind == "on_tool_end":
                yield SSEEvent(
                    type="tool_end",
                    data={"tool": name},
                ).to_sse()

    except Exception as exc:
        logger.error("Chat stream error", error=str(exc), conversation_id=conv_id)
        yield SSEEvent(type="error", data={"detail": "An error occurred during streaming."}).to_sse()
    finally:
        full_response = "".join(assistant_content_parts)
        if full_response:
            assistant_msg = Message(
                conversation_id=conv.id,
                role="assistant",
                content=full_response,
            )
            db.add(assistant_msg)
            await db.commit()

        yield SSEEvent(type="done").to_sse()


async def _get_or_create_conversation(
    user: User,
    conversation_id: uuid.UUID | None,
    db: AsyncSession,
) -> Conversation:
    if conversation_id:
        result = await db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user.id,
            )
        )
        conv = result.scalar_one_or_none()
        if conv:
            return conv

    conv = Conversation(user_id=user.id, status="active")
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return conv
