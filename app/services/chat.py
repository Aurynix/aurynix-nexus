import asyncio
import uuid
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

from langchain_core.messages import AIMessageChunk, HumanMessage
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
            "db": db,
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
        "next_agent": None,
        "agent_responded": False,
    }

    yield SSEEvent(
        type="metadata",
        data={"conversation_id": conv_id},
    ).to_sse()

    assistant_content_parts: list[str] = []
    first_token_sent = False
    stream_start = asyncio.get_event_loop().time()

    from app.core.metrics import active_connections, chat_latency_seconds, chat_requests_total

    active_connections.inc()
    try:
        async for event in graph.astream_events(input_state, config=config, version="v2"):
            kind = event["event"]
            name = event.get("name", "")
            data: dict[str, Any] = event.get("data", {})

            # Only stream tokens from sub-agent LLM calls, not the supervisor
            # (supervisor outputs JSON routing decisions, not user-facing text).
            # In LangGraph astream_events v2, the node name is in metadata["langgraph_node"];
            # event["name"] is the LLM class name (e.g. "ChatGroq"), not the node name.
            langgraph_node = event.get("metadata", {}).get("langgraph_node", "")
            is_subagent_llm = langgraph_node in ("research_agent", "email_agent", "calendar_agent")

            if kind == "on_chat_model_start" and is_subagent_llm:
                yield SSEEvent(type="agent_start", data={"agent": langgraph_node}).to_sse()

            elif kind == "on_chat_model_stream" and is_subagent_llm:
                chunk = data.get("chunk")
                if isinstance(chunk, AIMessageChunk) and chunk.content:
                    token = chunk.content
                    assistant_content_parts.append(token)
                    if not first_token_sent:
                        chat_latency_seconds.observe(asyncio.get_event_loop().time() - stream_start)
                        first_token_sent = True
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
        chat_requests_total.labels(status="error").inc()
        yield SSEEvent(
            type="error", data={"detail": "An error occurred during streaming."}
        ).to_sse()
    else:
        chat_requests_total.labels(status="success").inc()
    finally:
        active_connections.dec()
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
