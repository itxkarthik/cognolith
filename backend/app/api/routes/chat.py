import json
import logging
from typing import Any

from app.api.deps import CurrentUser, SessionDep
from app.core.websocket import manager
from app.models.chat import ChatMessages, ChatSession
from app.schemas.chat import ChatCreate, ChatMessageCreate, ChatMessageResponse, ChatResponse
from app.schemas.error import StandardErrorResponse
from app.schemas.note import NoteResponse
from app.services.chat_service import (
    convert_chat_to_note,
    create_chat_session,
    get_chat_session_by_id,
    list_chat_sessions,
    send_message_and_get_response,
    stream_message_and_get_response,
)
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatSessionListResponse(BaseModel):
    data: list[ChatResponse]
    count: int
    page_size: int
    has_more: bool


class ConvertChatToNoteRequest(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    folder_id: int | None = None


def _to_chat_message_response(message: ChatMessages) -> ChatMessageResponse:
    return ChatMessageResponse(
        id=message.id,
        session_id=message.session_id,
        role=str(message.role),
        content=message.content,
        model_used=message.model_used,
        tokens_used=message.tokens_used,
        response_time_ms=message.response_time_ms,
        sources=message.sources,
        created_at=message.created_at,
        updated_at=message.updated_at,
    )


def _to_chat_response(chat_session: ChatSession) -> ChatResponse:
    return ChatResponse(
        id=chat_session.id,
        user_id=chat_session.user_id,
        title=chat_session.title,
        description=chat_session.description,
        is_archived=chat_session.is_archived,
        is_pinned=chat_session.is_pinned,
        last_message_at=chat_session.last_message_at,
        created_at=chat_session.created_at,
        updated_at=chat_session.updated_at,
        messages=[_to_chat_message_response(message) for message in chat_session.messages],
    )


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
        400: {"model": StandardErrorResponse, "description": "Invalid query parameters"},
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
    return StreamingResponse(
        stream_message_and_get_response(
            session=session,
            current_user=current_user,
            chat_session_id=session_id,
            payload=body,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable proxy buffering for Nginx/Apache
        },
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
    """
    WebSocket endpoint for real-time chat messaging.

    Connection flow:
    1. Client connects with authentication token in query params
    2. Server validates token and establishes connection
    3. Client receives existing message history
    4. Messages are broadcast to all connected users in session

    Message format:
    {
        "type": "message" | "connection" | "error",
        "content": "...",
        "sender_id": user_id,
        "timestamp": ISO datetime,
        ...
    }
    """
    # TODO: Extract and validate authentication token from query params
    # For now, accept all connections (in production, validate JWT)
    user_id = 1  # Placeholder: extract from token

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
            message_data = json.loads(data)

            # Broadcast message to session
            await manager.broadcast_to_session(
                session_id,
                {
                    "type": "message",
                    "content": message_data.get("content"),
                    "sender_id": user_id,
                    "timestamp": __import__("datetime")
                    .datetime.now(__import__("datetime").timezone.utc)
                    .isoformat(),
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

    except Exception as e:
        logger.exception(f"WebSocket error in session {session_id}: {e}")
        manager.disconnect(session_id, user_id)
