import json
import logging
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any, Literal

import jwt
from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from jwt.exceptions import InvalidTokenError
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlmodel import Session, select

from app.api.deps import CurrentUser, SessionDep
from app.core import security
from app.core.config import settings
from app.core.database import engine
from app.core.websocket import manager
from app.models.chat import ChatGenerationStatus, ChatMessages, ChatRole, ChatSession
from app.models.user import TokenBlacklist, TokenPayload, User
from app.schemas.chat import (
    ChatCreate,
    ChatMessageCreate,
    ChatMessageResponse,
    ChatResponse,
    ChatSources,
)
from app.schemas.error import StandardErrorResponse
from app.schemas.note import NoteResponse
from app.services.chat_generation import (
    create_generation_messages,
    create_retry_message,
    generation_coordinator,
    stream_chat_generation,
)
from app.services.chat_service import (
    convert_chat_to_note,
    create_chat_session,
    get_chat_session_by_id,
    list_chat_sessions,
    send_message_and_get_response,
)

logger = logging.getLogger(__name__)


async def _stream_generated_chat_response(
    *, user_id: int, session_id: int, user_message_id: int, assistant_message_id: int
) -> AsyncGenerator[str, None]:
    yield ": connected\n\n"
    async for event in stream_chat_generation(
        user_id=user_id,
        session_id=session_id,
        user_message_id=user_message_id,
        assistant_message_id=assistant_message_id,
    ):
        yield event


router = APIRouter(prefix="/chat", tags=["chat"])


class ChatSessionListResponse(BaseModel):
    data: list[ChatResponse]
    count: int
    page_size: int
    has_more: bool


class ConvertChatToNoteRequest(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    folder_id: int | None = None


class WebSocketChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["message"]
    content: str = Field(min_length=1, max_length=settings.WEBSOCKET_MAX_CONTENT_LENGTH)

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Message content cannot be empty")
        return normalized


def _is_allowed_websocket_origin(origin: str | None) -> bool:
    if not origin:
        return False
    normalized = origin.rstrip("/")
    return normalized in settings.all_cors_origins


def _parse_websocket_message(data: str) -> WebSocketChatMessage:
    if len(data.encode("utf-8")) > settings.WEBSOCKET_MAX_MESSAGE_SIZE:
        raise ValueError("WebSocket message is too large")
    return WebSocketChatMessage.model_validate_json(data)


async def _authenticate_websocket(websocket: WebSocket, session_id: int) -> int | None:
    if not _is_allowed_websocket_origin(websocket.headers.get("origin")):
        await websocket.close(code=4403, reason="Origin not allowed")
        return None

    token = websocket.cookies.get(settings.ACCESS_TOKEN_COOKIE_NAME)
    if not token:
        await websocket.close(code=4401, reason="Authentication required")
        return None

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[security.ALGORITHM])
        token_data = TokenPayload(**payload)
        user_id = int(token_data.sub) if token_data.sub else None
    except (InvalidTokenError, ValueError, TypeError):
        await websocket.close(code=4401, reason="Invalid authentication")
        return None

    if user_id is None:
        await websocket.close(code=4401, reason="Invalid authentication")
        return None

    with Session(engine) as session:
        if (
            token_data.jti
            and session.exec(
                select(TokenBlacklist).where(TokenBlacklist.jti == token_data.jti)
            ).first()
        ):
            await websocket.close(code=4401, reason="Authentication revoked")
            return None

        user = session.get(User, user_id)
        chat_session = session.exec(
            select(ChatSession).where(
                ChatSession.id == session_id,
                ChatSession.user_id == user_id,
            )
        ).first()
        if not user or not user.is_active or not user.is_verified or not chat_session:
            await websocket.close(code=4403, reason="Access denied")
            return None

    return user_id


def _to_chat_message_response(message: ChatMessages) -> ChatMessageResponse:
    return ChatMessageResponse(
        id=_require_id(message.id, "Chat message"),
        session_id=_require_id(message.session_id, "Chat session"),
        role=(message.role.value if isinstance(message.role, ChatRole) else str(message.role)),
        content=message.content,
        model_used=message.model_used,
        tokens_used=message.tokens_used,
        response_time_ms=message.response_time_ms,
        sources=ChatSources.model_validate(message.sources) if message.sources else None,
        generation_status=(
            message.generation_status.value
            if isinstance(message.generation_status, ChatGenerationStatus)
            else message.generation_status
        ),
        generation_error=message.generation_error,
        generation_metadata=message.generation_metadata,
        generation_started_at=message.generation_started_at,
        generation_completed_at=message.generation_completed_at,
        created_at=message.created_at,
        updated_at=message.updated_at,
    )


def _to_chat_response(chat_session: ChatSession) -> ChatResponse:
    return ChatResponse(
        id=_require_id(chat_session.id, "Chat session"),
        user_id=_require_id(chat_session.user_id, "User"),
        title=chat_session.title,
        description=chat_session.description,
        is_archived=chat_session.is_archived,
        is_pinned=chat_session.is_pinned,
        last_message_at=chat_session.last_message_at,
        created_at=chat_session.created_at,
        updated_at=chat_session.updated_at,
        messages=[_to_chat_message_response(message) for message in chat_session.messages],
    )


def _require_id(value: int | None, entity_name: str) -> int:
    if value is None:
        raise RuntimeError(f"{entity_name} must be persisted before serialization")
    return value


def _to_note_response(note: Any) -> NoteResponse:
    return NoteResponse(
        id=note.id,
        user_id=note.user_id,
        folder_id=note.folder_id,
        title=note.title,
        content=note.content,
        content_type=note.content_type,
        summary=note.summary,
        keywords=note.keywords or [],
        tag_ids=[tag.id for tag in note.tags],
        linked_note_ids=[link.target_note_id for link in note.source_links],
        version=note.version,
        is_favorite=note.is_favorite,
        is_archived=note.is_archived,
        is_pinned=note.is_pinned,
        is_deleted=note.is_deleted,
        linked_document_id=note.linked_document_id,
        linked_chat_session_id=note.linked_chat_session_id,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


@router.post(
    path="/sessions",
    response_model=ChatResponse,
    responses={
        400: {"model": StandardErrorResponse, "description": "Validation error"},
        401: {"model": StandardErrorResponse, "description": "Authentication required"},
        500: {"model": StandardErrorResponse, "description": "Internal server error"},
    },
)
def create_chat_session_endpoint(
    *, session: SessionDep, current_user: CurrentUser, body: ChatCreate
) -> Any:
    chat_session = create_chat_session(session=session, current_user=current_user, payload=body)
    return _to_chat_response(chat_session)


@router.get(
    path="/sessions",
    response_model=ChatSessionListResponse,
    responses={
        400: {
            "model": StandardErrorResponse,
            "description": "Invalid query parameters",
        },
        401: {"model": StandardErrorResponse, "description": "Authentication required"},
        500: {"model": StandardErrorResponse, "description": "Internal server error"},
    },
)
def list_chat_sessions_endpoint(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> Any:
    sessions, count = list_chat_sessions(
        session=session,
        current_user=current_user,
        skip=skip,
        limit=limit,
    )
    has_more = (skip + limit) < count
    return ChatSessionListResponse(
        data=[_to_chat_response(item) for item in sessions],
        count=count,
        page_size=limit,
        has_more=has_more,
    )


@router.get(
    path="/sessions/{session_id}",
    response_model=ChatResponse,
    responses={
        401: {"model": StandardErrorResponse, "description": "Authentication required"},
        403: {"model": StandardErrorResponse, "description": "Access denied"},
        404: {"model": StandardErrorResponse, "description": "Chat session not found"},
        500: {"model": StandardErrorResponse, "description": "Internal server error"},
    },
)
def get_chat_session_endpoint(
    *, session: SessionDep, current_user: CurrentUser, session_id: int
) -> Any:
    chat_session = get_chat_session_by_id(
        session=session,
        current_user=current_user,
        chat_session_id=session_id,
    )
    return _to_chat_response(chat_session)


@router.post(
    path="/sessions/{session_id}/messages",
    response_model=ChatMessageResponse,
    responses={
        400: {"model": StandardErrorResponse, "description": "Validation error"},
        401: {"model": StandardErrorResponse, "description": "Authentication required"},
        403: {"model": StandardErrorResponse, "description": "Access denied"},
        404: {"model": StandardErrorResponse, "description": "Chat session not found"},
        409: {
            "model": StandardErrorResponse,
            "description": "A reply is already being generated",
        },
        500: {"model": StandardErrorResponse, "description": "Internal server error"},
        503: {"model": StandardErrorResponse, "description": "LLM service unavailable"},
    },
)
def send_message_endpoint(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    session_id: int,
    body: ChatMessageCreate,
) -> Any:
    _, assistant_message = send_message_and_get_response(
        session=session,
        current_user=current_user,
        chat_session_id=session_id,
        payload=body,
    )
    return _to_chat_message_response(assistant_message)


@router.post(
    path="/sessions/{session_id}/messages/stream",
    responses={
        200: {"description": "Server-Sent Events stream of chat response"},
        400: {"model": StandardErrorResponse, "description": "Validation error"},
        401: {"model": StandardErrorResponse, "description": "Authentication required"},
        403: {"model": StandardErrorResponse, "description": "Access denied"},
        404: {"model": StandardErrorResponse, "description": "Chat session not found"},
        409: {
            "model": StandardErrorResponse,
            "description": "A reply is already being generated",
        },
        500: {"model": StandardErrorResponse, "description": "Internal server error"},
        503: {"model": StandardErrorResponse, "description": "LLM service unavailable"},
    },
)
async def stream_message_endpoint(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    session_id: int,
    body: ChatMessageCreate,
) -> StreamingResponse:
    """
    Stream chat response using Server-Sent Events (SSE).

    Response format:
    - Each chunk: `data: <text>\n\n`
    - Completion marker: `data: [DONE]\n\n`

    Client should:
    1. Connect to this endpoint
    2. Parse SSE events
    3. Stop when receiving `[DONE]` marker
    """
    if current_user.id is None:
        raise ValueError("Authenticated user has no id")
    chat_session = get_chat_session_by_id(
        session=session, current_user=current_user, chat_session_id=session_id
    )
    user_message, assistant_message, _ = create_generation_messages(
        session=session,
        user=current_user,
        chat_session=chat_session,
        content=body.content,
    )
    if user_message.id is None or assistant_message.id is None:
        raise RuntimeError("Streaming messages were not persisted")
    return StreamingResponse(
        _stream_generated_chat_response(
            user_id=current_user.id,
            session_id=session_id,
            user_message_id=user_message.id,
            assistant_message_id=assistant_message.id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable proxy buffering for Nginx/Apache
        },
    )


@router.post(path="/sessions/{session_id}/messages/{message_id}/cancel")
def cancel_message_endpoint(
    *, session: SessionDep, current_user: CurrentUser, session_id: int, message_id: int
) -> dict[str, str]:
    get_chat_session_by_id(session=session, current_user=current_user, chat_session_id=session_id)
    message = session.get(ChatMessages, message_id)
    if message is None or message.session_id != session_id or message.role != ChatRole.assistant:
        raise HTTPException(status_code=404, detail="Assistant message not found")
    if not generation_coordinator.cancel(message_id):
        raise HTTPException(status_code=409, detail="This reply is not currently generating.")
    return {"message": "Cancellation requested."}


@router.post(path="/sessions/{session_id}/messages/{message_id}/retry/stream")
async def retry_message_endpoint(
    *, session: SessionDep, current_user: CurrentUser, session_id: int, message_id: int
) -> StreamingResponse:
    if current_user.id is None:
        raise ValueError("Authenticated user has no id")
    chat_session = get_chat_session_by_id(
        session=session, current_user=current_user, chat_session_id=session_id
    )
    user_message, assistant_message, _ = create_retry_message(
        session=session,
        user=current_user,
        chat_session=chat_session,
        failed_message_id=message_id,
    )
    if user_message.id is None or assistant_message.id is None:
        raise RuntimeError("Retry messages were not persisted")
    return StreamingResponse(
        _stream_generated_chat_response(
            user_id=current_user.id,
            session_id=session_id,
            user_message_id=user_message.id,
            assistant_message_id=assistant_message.id,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    path="/sessions/{session_id}/to-note",
    response_model=NoteResponse,
    responses={
        400: {"model": StandardErrorResponse, "description": "Validation error"},
        401: {"model": StandardErrorResponse, "description": "Authentication required"},
        403: {"model": StandardErrorResponse, "description": "Access denied"},
        404: {"model": StandardErrorResponse, "description": "Chat session not found"},
        500: {"model": StandardErrorResponse, "description": "Internal server error"},
    },
)
def convert_chat_to_note_endpoint(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    session_id: int,
    body: ConvertChatToNoteRequest,
) -> Any:
    note = convert_chat_to_note(
        session=session,
        current_user=current_user,
        chat_session_id=session_id,
        title=body.title,
        folder_id=body.folder_id,
    )
    return _to_note_response(note)


@router.websocket("/sessions/{session_id}/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: int,
) -> None:
    user_id = await _authenticate_websocket(websocket, session_id)
    if user_id is None:
        return

    await manager.connect(websocket, session_id, user_id)

    try:
        # Send connection confirmation
        await manager.send_to_user(
            session_id,
            user_id,
            {
                "type": "connection",
                "status": "connected",
                "session_id": session_id,
                "user_count": manager.get_session_user_count(session_id),
            },
        )

        # Listen for incoming messages
        while True:
            data = await websocket.receive_text()
            message_data = _parse_websocket_message(data)

            # Broadcast message to session
            await manager.broadcast_to_session(
                session_id,
                {
                    "type": "message",
                    "content": message_data.content,
                    "sender_id": user_id,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )

    except WebSocketDisconnect:
        manager.disconnect(session_id, user_id)
        logger.info(f"WebSocket disconnected: session={session_id}, user={user_id}")

        # Notify other users in session
        if manager.has_active_connections(session_id):
            await manager.broadcast_to_session(
                session_id,
                {
                    "type": "user_left",
                    "user_id": user_id,
                    "user_count": manager.get_session_user_count(session_id),
                },
            )

    except (ValueError, json.JSONDecodeError):
        await websocket.close(code=1008, reason="Invalid message")
        manager.disconnect(session_id, user_id)
    except Exception:
        logger.exception("WebSocket error in session %s", session_id)
        manager.disconnect(session_id, user_id)
