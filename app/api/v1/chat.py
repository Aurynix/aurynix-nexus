import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.core.dependencies import CurrentUser, DbSession
from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.models.conversation import Conversation
from app.schemas.chat import ChatRequest, ConversationDetailResponse, ConversationResponse
from app.services.chat import stream_chat

if TYPE_CHECKING:
    from langgraph.graph.graph import CompiledGraph

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/stream")
async def chat_stream(
    body: ChatRequest,
    current_user: CurrentUser,
    db: DbSession,
    request: Request,
) -> StreamingResponse:
    graph: CompiledGraph = request.app.state.graph

    return StreamingResponse(
        stream_chat(
            graph=graph,
            user=current_user,
            message=body.message,
            conversation_id=body.conversation_id,
            db=db,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/conversations", response_model=list[ConversationResponse])
async def list_conversations(
    current_user: CurrentUser, db: DbSession
) -> list[ConversationResponse]:
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == current_user.id)
        .order_by(Conversation.updated_at.desc())
    )
    convs = result.scalars().all()
    return [ConversationResponse.model_validate(c) for c in convs]


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(
    conversation_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> ConversationDetailResponse:
    from sqlalchemy.orm import selectinload

    result = await db.execute(
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(Conversation.id == conversation_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise NotFoundError("Conversation not found.").to_http_exception()
    if conv.user_id != current_user.id:
        raise PermissionDeniedError().to_http_exception()
    return ConversationDetailResponse.model_validate(conv)


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> None:
    result = await db.execute(select(Conversation).where(Conversation.id == conversation_id))
    conv = result.scalar_one_or_none()
    if not conv:
        raise NotFoundError("Conversation not found.").to_http_exception()
    if conv.user_id != current_user.id:
        raise PermissionDeniedError().to_http_exception()
    await db.delete(conv)
    await db.commit()
