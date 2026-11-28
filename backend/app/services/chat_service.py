from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, true
from sqlalchemy.orm import joinedload
from sqlmodel import Session, col, select

from app.ai.rag import RAGResult, run_rag_pipeline
from app.core.exceptions import AIServiceUnavailableError
from app.models.chat import ChatMessages, ChatRole, ChatSession
from app.models.note import Notes
from app.models.user import User
from app.schemas.chat import ChatCreate, ChatMessageCreate, ChatMessagePreview, ChatSessionSummary
from app.services.chat_generation import generation_coordinator
from app.services.chat_history import build_conversation_history
from app.utils.text_processing import create_content_preview

logger = logging.getLogger(__name__)


def _acquire_chat_generation_lock(
    *, session: Session, chat_session_id: int
) -> AbstractContextManager[None]:
    """
    Reserve the chat session through the same coordinator the streaming path uses,
    so a streaming and a non-streaming reply can never run in one session at once.
    Raises 409 immediately when another reply is in progress.
    """
    return generation_coordinator.exclusive(session_id=chat_session_id)


def create_chat_session(
    *, session: Session, current_user: User, payload: ChatCreate
) -> ChatSession:
    chat_session = ChatSession(
        user_id=current_user.id,
        title=payload.title,
        description=payload.description,
    )
    session.add(chat_session)
    session.commit()
    session.refresh(chat_session)
    if chat_session.id is None:
        raise RuntimeError("Chat session must be persisted before use")
    chat_session_id = chat_session.id

    # Re-fetch with eager-loaded messages to avoid lazy loading issues
    chat_session = (
        session.exec(
            select(ChatSession)
            .where(ChatSession.id == chat_session_id)
            .options(joinedload(ChatSession.messages))  # pyright: ignore[reportArgumentType]
        )
        .unique()
        .first()
    )

    if chat_session is None:
        raise RuntimeError("Persisted chat session could not be reloaded")
    return chat_session


# Characters of the last message returned with a listed session
LAST_MESSAGE_PREVIEW_CHARS = 300


def list_chat_sessions(
    *, session: Session, current_user: User, skip: int = 0, limit: int = 20
) -> tuple[list[ChatSessionSummary], int]:
    """
    One page of the user's chat sessions, newest activity first, without their messages.

    Each session carries its message count and the start of its last non-empty
    message, both computed in the query: the sidebar used to load every message of
    every listed session just to show one line.
    """
    total_count = (
        session.exec(
            select(func.count())
            .select_from(ChatSession)
            .where(ChatSession.user_id == current_user.id)
        ).one()
        or 0
    )

    message_count = (
        select(func.count())
        .select_from(ChatMessages)
        .where(ChatMessages.session_id == ChatSession.id)
        .scalar_subquery()
    )
    # Uses ix_chat_messages_session_created; an empty reply still streaming is skipped
    last_message = (
        select(
            col(ChatMessages.role).label("role"),
            func.left(ChatMessages.content, LAST_MESSAGE_PREVIEW_CHARS).label("preview"),
        )
        .where(
            ChatMessages.session_id == ChatSession.id,
            func.length(func.btrim(ChatMessages.content)) > 0,
        )
        .order_by(col(ChatMessages.created_at).desc(), col(ChatMessages.id).desc())
        .limit(1)
        .lateral("last_message")
    )
    rows = session.exec(
        select(
            ChatSession,
            message_count.label("message_count"),
            last_message.c.role,
            last_message.c.preview,
        )
        .outerjoin(last_message, true())
        .where(ChatSession.user_id == current_user.id)
        .order_by(col(ChatSession.last_message_at).desc(), col(ChatSession.id).desc())
        .limit(limit)
        .offset(skip)
    ).all()
    return [_session_summary(*row) for row in rows], total_count


def _session_summary(
    chat_session: ChatSession,
    message_count: int,
    role: object,
    preview: str | None,
) -> ChatSessionSummary:
    if chat_session.id is None or chat_session.user_id is None:
        raise RuntimeError("Chat session must be persisted before listing")
    last = (
        ChatMessagePreview(
            role=role.value if isinstance(role, ChatRole) else str(role),
            content=preview,
        )
        if preview is not None
        else None
    )
    return ChatSessionSummary(
        id=chat_session.id,
        user_id=chat_session.user_id,
        title=chat_session.title,
        description=chat_session.description,
        is_archived=chat_session.is_archived,
        is_pinned=chat_session.is_pinned,
        last_message_at=chat_session.last_message_at,
        created_at=chat_session.created_at,
        updated_at=chat_session.updated_at,
        message_count=message_count,
        last_message=last,
    )


def send_message_and_get_response(
    *,
    session: Session,
    current_user: User,
    chat_session_id: int,
    payload: ChatMessageCreate,
) -> tuple[ChatMessages, ChatMessages]:
    chat_session = get_chat_session_by_id(
        session=session,
        current_user=current_user,
        chat_session_id=chat_session_id,
    )
    if chat_session.id is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    with _acquire_chat_generation_lock(session=session, chat_session_id=chat_session.id):
        return _generate_and_store_reply(
            session=session,
            current_user=current_user,
            chat_session=chat_session,
            payload=payload,
        )


def _generate_and_store_reply(
    *,
    session: Session,
    current_user: User,
    chat_session: ChatSession,
    payload: ChatMessageCreate,
) -> tuple[ChatMessages, ChatMessages]:
    if chat_session.id is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    try:
        rag_result = _invoke_rag(
            session=session,
            current_user=current_user,
            query=payload.content,
            conversation_history=build_conversation_history(
                getattr(chat_session, "messages", [])
            ),
        )
    except Exception as exc:
        session.rollback()
        logger.exception("RAG pipeline failed for chat session %s", chat_session.id)
        raise AIServiceUnavailableError() from exc

    user_message = ChatMessages(
        session_id=chat_session.id,
        role=ChatRole.user,
        content=payload.content,
    )
    session.add(user_message)

    assistant_message = ChatMessages(
        session_id=chat_session.id,
        role=ChatRole.assistant,
        content=rag_result.answer,
        model_used="rag-v1",
        sources=rag_result.sources,
        tokens_used=rag_result.generated_tokens,
    )
    session.add(assistant_message)

    chat_session.last_message_at = datetime.now(UTC)
    if not chat_session.title:
        chat_session.title = create_content_preview(payload.content, max_length=80)
    session.add(chat_session)

    session.commit()
    session.refresh(assistant_message)
    return user_message, assistant_message


def convert_chat_to_note(
    *,
    session: Session,
    current_user: User,
    chat_session_id: int,
    title: str | None = None,
    folder_id: int | None = None,
) -> Notes:
    chat_session = get_chat_session_by_id(
        session=session,
        current_user=current_user,
        chat_session_id=chat_session_id,
    )
    messages = session.exec(
        select(ChatMessages)
        .where(ChatMessages.session_id == chat_session.id)
        .order_by(col(ChatMessages.created_at).asc())
    ).all()
    if not messages:
        raise HTTPException(status_code=400, detail="Cannot convert empty chat session to note")

    if folder_id is not None:
        folder_exists = session.exec(
            select(Notes).where(Notes.user_id == current_user.id, Notes.folder_id == folder_id)
        ).first()
        if folder_exists is None:
            from app.models.note import NoteFolders

            folder = session.exec(
                select(NoteFolders).where(
                    NoteFolders.id == folder_id,
                    NoteFolders.user_id == current_user.id,
                    col(NoteFolders.is_deleted).is_not(True),
                )
            ).first()
            if not folder:
                raise HTTPException(status_code=404, detail="Folder not found")

    content_lines = [f"### {message.role.title()}\n{message.content}" for message in messages]
    note_content = "\n\n".join(content_lines)
    note_title = title or chat_session.title or f"Chat Session {chat_session.id}"

    note = Notes(
        user_id=current_user.id,
        folder_id=folder_id,
        title=note_title,
        content=note_content,
        content_preview=create_content_preview(note_content, max_length=200),
        content_type="markdown",
        linked_chat_session_id=chat_session.id,
        word_count=len(note_content.split()),
        char_count=len(note_content),
        read_time_minutes=max(1, len(note_content.split()) // 200),
    )
    session.add(note)
    session.commit()
    session.refresh(note)
    return note


def get_chat_session_by_id(
    *, session: Session, current_user: User, chat_session_id: int
) -> ChatSession:
    chat_session = (
        session.exec(
            select(ChatSession)
            .where(
                ChatSession.id == chat_session_id,
                ChatSession.user_id == current_user.id,
            )
            .options(joinedload(ChatSession.messages))  # pyright: ignore[reportArgumentType]
        )
        .unique()
        .first()
    )
    if not chat_session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return chat_session


def _invoke_rag(
    *,
    session: Session,
    current_user: User,
    query: str,
    conversation_history: list[dict[str, Any]] | None = None,
) -> RAGResult:
    if current_user.id is None:
        raise HTTPException(status_code=400, detail="Invalid user context")

    return run_rag_pipeline(
        session=session,
        user_id=current_user.id,
        query=query,
        conversation_history=conversation_history,
    )


async def stream_message_response(*, assistant_message: ChatMessages) -> AsyncGenerator[str, None]:
    """
    Stream chat response with Server-Sent Events (SSE) format.

    Yields:
        str: Text chunks in SSE format (e.g., "data: hello world\n\n")
        Final yield: "data: [DONE]\n\n" to signal completion
    """
    escaped_response = assistant_message.content.replace("\n", "\\n")
    yield f"data: {escaped_response}\n\n"
    yield "data: [DONE]\n\n"
