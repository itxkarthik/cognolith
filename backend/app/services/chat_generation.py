from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from threading import Event, Lock
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session, col, select

from app.ai.grounding import build_grounding_repair_messages, validate_grounded_answer
from app.ai.llm import LLMService
from app.ai.rag import finalize_prepared_answer, prepare_rag_pipeline
from app.core.database import engine
from app.models.chat import ChatGenerationStatus, ChatMessages, ChatRole, ChatSession
from app.models.user import User, UserSettings


def encode_sse(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"


class GenerationCoordinator:
    def __init__(self) -> None:
        self._lock = Lock()
        self._by_message: dict[int, Event] = {}
        self._by_session: dict[int, int] = {}

    def start(self, *, session_id: int, message_id: int) -> Event:
        with self._lock:
            if session_id in self._by_session:
                raise HTTPException(
                    status_code=409,
                    detail="A reply is already being generated for this chat session.",
                )
            event = Event()
            self._by_session[session_id] = message_id
            self._by_message[message_id] = event
            return event

    def is_session_active(self, session_id: int) -> bool:
        with self._lock:
            return session_id in self._by_session

    def cancel(self, message_id: int) -> bool:
        with self._lock:
            event = self._by_message.get(message_id)
            if event is None:
                return False
            event.set()
            return True

    def cancellation_event(self, message_id: int) -> Event | None:
        with self._lock:
            return self._by_message.get(message_id)

    def finish(self, *, session_id: int, message_id: int) -> None:
        with self._lock:
            self._by_message.pop(message_id, None)
            if self._by_session.get(session_id) == message_id:
                self._by_session.pop(session_id, None)


generation_coordinator = GenerationCoordinator()


def _message_payload(message: ChatMessages) -> dict[str, Any]:
    def iso(value: datetime | None) -> str | None:
        return value.isoformat() if value else None

    return {
        "id": message.id,
        "session_id": message.session_id,
        "role": message.role.value if isinstance(message.role, ChatRole) else str(message.role),
        "content": message.content,
        "model_used": message.model_used,
        "tokens_used": message.tokens_used,
        "response_time_ms": message.response_time_ms,
        "sources": message.sources,
        "generation_status": (
            message.generation_status.value
            if isinstance(message.generation_status, ChatGenerationStatus)
            else message.generation_status
        ),
        "generation_error": message.generation_error,
        "generation_metadata": message.generation_metadata,
        "generation_started_at": iso(message.generation_started_at),
        "generation_completed_at": iso(message.generation_completed_at),
        "created_at": iso(message.created_at),
        "updated_at": iso(message.updated_at),
    }


def create_generation_messages(
    *, session: Session, user: User, chat_session: ChatSession, content: str
) -> tuple[ChatMessages, ChatMessages, Event]:
    if chat_session.id is None or user.id is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    if generation_coordinator.is_session_active(chat_session.id):
        raise HTTPException(status_code=409, detail="A reply is already being generated.")
    now = datetime.now(UTC)
    user_message = ChatMessages(session_id=chat_session.id, role=ChatRole.user, content=content)
    assistant = ChatMessages(
        session_id=chat_session.id,
        role=ChatRole.assistant,
        content="",
        model_used="rag-v2-stream",
        generation_status=ChatGenerationStatus.streaming,
        generation_started_at=now,
    )
    session.add(user_message)
    session.add(assistant)
    chat_session.last_message_at = now
    if not chat_session.title:
        chat_session.title = content[:80]
    session.add(chat_session)
    session.commit()
    session.refresh(user_message)
    session.refresh(assistant)
    if assistant.id is None:
        raise RuntimeError("Assistant message was not persisted")
    try:
        cancellation = generation_coordinator.start(
            session_id=chat_session.id, message_id=assistant.id
        )
    except Exception:
        assistant.generation_status = ChatGenerationStatus.failed
        assistant.generation_error = "Generation could not be started."
        assistant.generation_completed_at = datetime.now(UTC)
        session.add(assistant)
        session.commit()
        raise
    return user_message, assistant, cancellation


def create_retry_message(
    *, session: Session, user: User, chat_session: ChatSession, failed_message_id: int
) -> tuple[ChatMessages, ChatMessages, Event]:
    failed = session.get(ChatMessages, failed_message_id)
    if (
        failed is None
        or failed.session_id != chat_session.id
        or failed.role != ChatRole.assistant
        or failed.generation_status
        not in {ChatGenerationStatus.cancelled, ChatGenerationStatus.failed}
    ):
        raise HTTPException(
            status_code=409, detail="Only stopped or failed replies can be retried."
        )
    user_message = session.exec(
        select(ChatMessages)
        .where(
            ChatMessages.session_id == chat_session.id,
            ChatMessages.role == ChatRole.user,
            col(ChatMessages.created_at) <= failed.created_at,
        )
        .order_by(col(ChatMessages.created_at).desc())
    ).first()
    if user_message is None:
        raise HTTPException(status_code=409, detail="The original user message was not found.")
    now = datetime.now(UTC)
    assistant = ChatMessages(
        session_id=chat_session.id,
        role=ChatRole.assistant,
        content="",
        model_used="rag-v2-stream",
        generation_status=ChatGenerationStatus.streaming,
        generation_started_at=now,
        generation_metadata={"retry_of": failed_message_id},
    )
    session.add(assistant)
    session.commit()
    session.refresh(assistant)
    if assistant.id is None or chat_session.id is None:
        raise RuntimeError("Retry message was not persisted")
    cancellation = generation_coordinator.start(session_id=chat_session.id, message_id=assistant.id)
    return user_message, assistant, cancellation


async def stream_chat_generation(
    *, user_id: int, session_id: int, user_message_id: int, assistant_message_id: int
) -> AsyncGenerator[str, None]:
    started = time.perf_counter()
    cancellation = generation_coordinator.cancellation_event(assistant_message_id)
    if cancellation is None:
        return
    draft = ""
    original_draft = ""
    with Session(engine) as session:
        user = session.get(User, user_id)
        user_message = session.get(ChatMessages, user_message_id)
        assistant = session.get(ChatMessages, assistant_message_id)
        if user is None or user_message is None or assistant is None:
            generation_coordinator.finish(session_id=session_id, message_id=assistant_message_id)
            return
        yield encode_sse(
            "generation_started",
            {
                "session_id": session_id,
                "user_message": _message_payload(user_message),
                "assistant_message": _message_payload(assistant),
            },
        )
        try:
            history_rows = session.exec(
                select(ChatMessages)
                .where(
                    ChatMessages.session_id == session_id,
                    col(ChatMessages.id) < user_message_id,
                )
                .order_by(col(ChatMessages.created_at).desc())
                .limit(6)
            ).all()
            history = [
                {
                    "role": row.role.value if isinstance(row.role, ChatRole) else str(row.role),
                    "content": row.content,
                    "sources": row.sources,
                }
                for row in reversed(history_rows)
            ]
            prepared = prepare_rag_pipeline(
                session=session,
                user_id=user_id,
                query=user_message.content,
                conversation_history=history,
            )
            preferences = session.get(UserSettings, user_id)
            diagnostics_enabled = bool(preferences and preferences.rag_diagnostics_enabled)
            yield encode_sse(
                "retrieval_complete",
                {
                    "message_id": assistant_message_id,
                    "diagnostics": prepared.diagnostics if diagnostics_enabled else None,
                },
            )
            llm = LLMService(session=session, user_id=user_id)
            pending_chars = 0
            async for delta in llm.stream_response(messages=prepared.messages):
                if cancellation.is_set():
                    break
                draft += delta
                pending_chars += len(delta)
                yield encode_sse("token", {"message_id": assistant_message_id, "delta": delta})
                if pending_chars >= 128:
                    assistant.content = draft
                    session.add(assistant)
                    session.commit()
                    pending_chars = 0

            if cancellation.is_set():
                assistant.content = draft
                assistant.generation_status = ChatGenerationStatus.cancelled
                assistant.generation_completed_at = datetime.now(UTC)
                session.add(assistant)
                session.commit()
                session.refresh(assistant)
                yield encode_sse("cancelled", {"message": _message_payload(assistant)})
                return

            original_draft = draft
            valid_ids = {source.citation_id for source in prepared.context_sources}
            validation = validate_grounded_answer(draft, valid_citation_ids=valid_ids)
            repair_attempted = prepared.grounded and not validation.is_valid
            if repair_attempted:
                yield encode_sse(
                    "answer_reset",
                    {"message_id": assistant_message_id, "reason": "grounding_repair"},
                )
                draft = ""
                repair_messages = build_grounding_repair_messages(
                    messages=prepared.messages,
                    draft=original_draft,
                    valid_citation_ids=valid_ids,
                )
                try:
                    async for delta in llm.stream_response(messages=repair_messages):
                        if cancellation.is_set():
                            break
                        draft += delta
                        yield encode_sse(
                            "token", {"message_id": assistant_message_id, "delta": delta}
                        )
                except Exception:
                    draft = original_draft

            if cancellation.is_set():
                assistant.content = draft
                assistant.generation_status = ChatGenerationStatus.cancelled
            else:
                final_answer, sources = finalize_prepared_answer(draft, prepared=prepared)
                assistant.content = final_answer
                assistant.sources = sources
                assistant.tokens_used = len(final_answer.split())
                assistant.response_time_ms = int((time.perf_counter() - started) * 1000)
                assistant.generation_status = ChatGenerationStatus.completed
                metadata = {
                    "repair_attempted": repair_attempted,
                    "validation": validation.reason or "valid",
                }
                if diagnostics_enabled:
                    metadata["retrieval"] = prepared.diagnostics
                assistant.generation_metadata = metadata
            assistant.generation_completed_at = datetime.now(UTC)
            session.add(assistant)
            session.commit()
            session.refresh(assistant)
            if assistant.generation_status == ChatGenerationStatus.cancelled:
                yield encode_sse("cancelled", {"message": _message_payload(assistant)})
            else:
                yield encode_sse(
                    "sources",
                    {"message_id": assistant_message_id, "sources": assistant.sources or {}},
                )
                yield encode_sse("completed", {"message": _message_payload(assistant)})
        except (asyncio.CancelledError, GeneratorExit):
            cancellation.set()
            assistant.content = draft or original_draft
            assistant.generation_status = ChatGenerationStatus.cancelled
            assistant.generation_completed_at = datetime.now(UTC)
            session.add(assistant)
            session.commit()
            raise
        except Exception as exc:
            assistant.content = draft or original_draft
            assistant.generation_status = ChatGenerationStatus.failed
            assistant.generation_error = "The AI response could not be completed."
            assistant.generation_completed_at = datetime.now(UTC)
            session.add(assistant)
            session.commit()
            yield encode_sse(
                "error",
                {
                    "code": "GENERATION_FAILED",
                    "message": str(exc),
                    "retryable": True,
                    "assistant_message_id": assistant_message_id,
                },
            )
        finally:
            generation_coordinator.finish(session_id=session_id, message_id=assistant_message_id)
