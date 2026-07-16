from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, text
from sqlalchemy.orm import joinedload
from sqlmodel import Session, col, select

from app.ai.rag import run_rag_pipeline
from app.core.exceptions import AIServiceUnavailableError
from app.models.chat import ChatMessages, ChatRole, ChatSession
from app.models.note import Notes
from app.models.user import User
from app.schemas.chat import ChatCreate, ChatMessageCreate
from app.utils.text_processing import create_content_preview

logger = logging.getLogger(__name__)


def _acquire_chat_generation_lock(*, session: Session, chat_session_id: int) -> None:
    result = (
        session.connection()
        .execute(
            text("SELECT pg_try_advisory_xact_lock(:namespace, :chat_session_id)"),
            parameters={"namespace": 5262145, "chat_session_id": chat_session_id},
        )
        .one()
    )
    if not bool(result[0]):
        raise HTTPException(
            status_code=409,
            detail="A reply is already being generated for this chat session.",
        )


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


def list_chat_sessions(
    *, session: Session, current_user: User, skip: int = 0, limit: int = 20
) -> tuple[list[ChatSession], int]:
    """
    List chat sessions with efficient pagination and eager message loading.

    Performance improvements:
    - Uses SQL COUNT(*) for efficient counting (not fetching all rows)
    - Uses database LIMIT/OFFSET instead of in-memory slicing
    - Eagerly loads messages with joinedload to prevent N+1 queries
    """
    # Get total count using efficient SQL COUNT
    count_statement = (
        select(func.count()).select_from(ChatSession).where(ChatSession.user_id == current_user.id)
    )
    total_count = session.exec(count_statement).one() or 0

    # Fetch chat sessions with eager-loaded messages and pagination
    statement = (
        select(ChatSession)
        .where(ChatSession.user_id == current_user.id)
        .order_by(col(ChatSession.last_message_at).desc())
        # Eagerly load messages to prevent N+1 query issue when accessing session.messages
        .options(joinedload(ChatSession.messages))  # pyright: ignore[reportArgumentType]
        .limit(limit)
        .offset(skip)
    )

    sessions = session.exec(statement).unique().all()
    return list(sessions), total_count


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
    _acquire_chat_generation_lock(session=session, chat_session_id=chat_session.id)

    try:
        rag_answer, rag_sources = _invoke_rag(
            session=session,
            current_user=current_user,
            query=payload.content,
            conversation_history=[
                {
                    "role": (
                        message.role.value
                        if isinstance(message.role, ChatRole)
                        else str(message.role)
                    ),
                    "content": message.content,
                    "sources": message.sources,
                }
                for message in getattr(chat_session, "messages", [])[-6:]
            ],
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
        content=rag_answer,
        model_used="rag-v1",
        sources=rag_sources,
        tokens_used=len(rag_answer.split()),
    )
    session.add(assistant_message)

    chat_session.last_message_at = datetime.now()
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
) -> tuple[str, dict]:
    if current_user.id is None:
        raise HTTPException(status_code=400, detail="Invalid user context")

    rag_result = run_rag_pipeline(
        session=session,
        user_id=current_user.id,
        query=query,
        conversation_history=conversation_history,
    )
    return rag_result.answer, rag_result.sources


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
