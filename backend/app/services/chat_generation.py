from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator, Callable
from datetime import UTC, datetime
from threading import Event
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session, col, select, update

from app.ai.grounding import build_grounding_repair_messages, validate_grounded_answer
from app.ai.llm import LLMService
from app.ai.rag import PreparedRAGResponse, finalize_prepared_answer, prepare_rag_pipeline
from app.core.database import engine
from app.models.chat import ChatGenerationStatus, ChatMessages, ChatRole, ChatSession
from app.models.user import User, UserSettings
from app.services.chat_history import REPLY_TO_KEY, build_conversation_history
from app.services.generation_coordinator import generation_coordinator

logger = logging.getLogger(__name__)

GENERATION_FAILED_MESSAGE = "The AI response could not be completed."
INTERRUPTED_MESSAGE = "The reply was interrupted. Retry to generate it again."
# Recent messages read to build the history (several attempts can share one question)
HISTORY_SCAN_LIMIT = 40


def encode_sse(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"


SSE_KEEPALIVE = ": keepalive\n\n"
SSE_KEEPALIVE_INTERVAL_SECONDS = 15.0


async def with_sse_keepalive(
    events: AsyncGenerator[str, None],
    *,
    interval: float = SSE_KEEPALIVE_INTERVAL_SECONDS,
) -> AsyncGenerator[str, None]:
    """
    Emit an SSE comment whenever no event arrives for `interval` seconds.

    Proxies (the Next.js rewrite included) drop connections that sit idle, and
    retrieval or model warm-up can be silent for longer than their timeout.
    """
    pending: asyncio.Future[str] | None = None
    try:
        while True:
            if pending is None:
                pending = asyncio.ensure_future(anext(events))
            done, _ = await asyncio.wait({pending}, timeout=interval)
            if not done:
                yield SSE_KEEPALIVE
                continue
            step, pending = pending, None
            try:
                event = step.result()
            except StopAsyncIteration:
                return
            yield event
    finally:
        # Client went away: cancel the in-flight step so the generator records the
        # reply as cancelled, then close it
        if pending is not None and not pending.done():
            pending.cancel()
            try:
                await pending
            except (asyncio.CancelledError, StopAsyncIteration):
                pass
        await events.aclose()


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


def ensure_no_active_generation(session_id: int) -> None:
    """
    Early 409 for the common case, before the response starts. The claim itself is
    taken when the stream runs, so a client that disconnects first leaves nothing held.
    """
    if generation_coordinator.is_session_active(session_id):
        raise HTTPException(status_code=409, detail="A reply is already being generated.")


def create_generation_messages(
    *, session: Session, user: User, chat_session: ChatSession, content: str
) -> tuple[ChatMessages, ChatMessages, Event]:
    if chat_session.id is None or user.id is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
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
    session.flush()
    # Retry binds to this, not to whichever user message happens to be newest
    assistant.generation_metadata = {REPLY_TO_KEY: user_message.id}
    session.add(assistant)
    chat_session.last_message_at = now
    if not chat_session.title:
        chat_session.title = content[:80]
    session.add(chat_session)
    cancellation = _claim_and_commit(session=session, session_id=chat_session.id, reply=assistant)
    session.refresh(user_message)
    return user_message, assistant, cancellation


def ensure_retryable(
    *, session: Session, chat_session: ChatSession, failed_message_id: int
) -> ChatMessages:
    """Return the question a stopped or failed reply answered, or raise 409."""
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
    if chat_session.id is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    ensure_no_active_generation(chat_session.id)
    user_message = _original_user_message(session=session, failed=failed)
    if user_message is None or user_message.id is None:
        raise HTTPException(status_code=409, detail="The original user message was not found.")
    return user_message


def create_retry_message(
    *, session: Session, user: User, chat_session: ChatSession, failed_message_id: int
) -> tuple[ChatMessages, ChatMessages, Event]:
    user_message = ensure_retryable(
        session=session, chat_session=chat_session, failed_message_id=failed_message_id
    )
    if chat_session.id is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    assistant = ChatMessages(
        session_id=chat_session.id,
        role=ChatRole.assistant,
        content="",
        model_used="rag-v2-stream",
        generation_status=ChatGenerationStatus.streaming,
        generation_started_at=datetime.now(UTC),
        generation_metadata={"retry_of": failed_message_id, REPLY_TO_KEY: user_message.id},
    )
    session.add(assistant)
    cancellation = _claim_and_commit(session=session, session_id=chat_session.id, reply=assistant)
    return user_message, assistant, cancellation


def _claim_and_commit(*, session: Session, session_id: int, reply: ChatMessages) -> Event:
    """
    Claim the chat session for `reply` before its rows are committed: losing the race
    rolls them back instead of leaving an orphan question or a reply stuck streaming.
    """
    session.flush()  # assigns the reply's id, which the claim is keyed on
    if reply.id is None:
        raise RuntimeError("Assistant message was not persisted")
    try:
        cancellation = generation_coordinator.start(session_id=session_id, message_id=reply.id)
    except HTTPException:
        session.rollback()
        raise
    try:
        session.commit()
    except Exception:
        session.rollback()
        generation_coordinator.finish(session_id=session_id, message_id=reply.id)
        raise
    session.refresh(reply)
    return cancellation


def fail_interrupted_generations(session: Session) -> int:
    """
    Mark replies left `streaming` by a crash or restart as failed, so they can be
    retried. Run at startup: claims live in this process's memory, so no reply can
    still be generating then.
    """
    result = session.exec(
        update(ChatMessages)
        .where(col(ChatMessages.generation_status) == ChatGenerationStatus.streaming)
        .values(
            generation_status=ChatGenerationStatus.failed,
            generation_error=INTERRUPTED_MESSAGE,
            generation_completed_at=datetime.now(UTC),
        )
    )
    session.commit()
    return result.rowcount or 0


def _original_user_message(*, session: Session, failed: ChatMessages) -> ChatMessages | None:
    reply_to = (failed.generation_metadata or {}).get(REPLY_TO_KEY)
    if isinstance(reply_to, int):
        message = session.get(ChatMessages, reply_to)
        if (
            message is not None
            and message.session_id == failed.session_id
            and message.role == ChatRole.user
        ):
            return message
        return None

    # Replies created before reply_to was recorded: follow retries back to the
    # first attempt, then take the user message just before it.
    origin = failed
    seen: set[int] = set()
    while (origin.generation_metadata or {}).get("retry_of") is not None:
        previous_id = (origin.generation_metadata or {})["retry_of"]
        if previous_id in seen:
            break
        seen.add(previous_id)
        previous = session.get(ChatMessages, previous_id)
        if previous is None or previous.session_id != failed.session_id:
            break
        origin = previous
    return session.exec(
        select(ChatMessages)
        .where(
            ChatMessages.session_id == failed.session_id,
            ChatMessages.role == ChatRole.user,
            col(ChatMessages.created_at) <= origin.created_at,
        )
        .order_by(col(ChatMessages.created_at).desc())
    ).first()


def _start_failed_event(message: str) -> str:
    return encode_sse(
        "error",
        {
            "code": "GENERATION_NOT_STARTED",
            "message": message,
            "retryable": False,
            "assistant_message_id": None,
        },
    )


def _prepare_rag_in_own_session(
    *, user_id: int, query: str, conversation_history: list[dict[str, Any]]
) -> PreparedRAGResponse:
    """
    Run retrieval in a worker thread with its own DB session. A cancelled stream
    stops awaiting the thread but can't stop it, so the two must not share a session.
    """
    with Session(engine) as rag_session:
        prepared = prepare_rag_pipeline(
            session=rag_session,
            user_id=user_id,
            query=query,
            conversation_history=conversation_history,
        )
        # Persist workspace embeddings refreshed during retrieval
        rag_session.commit()
        return prepared


BeginReply = Callable[[Session, User, ChatSession], tuple[ChatMessages, ChatMessages, Event]]


def stream_new_reply(*, user_id: int, session_id: int, content: str) -> AsyncGenerator[str, None]:
    """Answer a new question; its rows are written once the stream runs."""

    def begin(
        session: Session, user: User, chat_session: ChatSession
    ) -> tuple[ChatMessages, ChatMessages, Event]:
        return create_generation_messages(
            session=session, user=user, chat_session=chat_session, content=content
        )

    return stream_chat_generation(user_id=user_id, session_id=session_id, begin=begin)


def stream_retry_reply(
    *, user_id: int, session_id: int, failed_message_id: int
) -> AsyncGenerator[str, None]:
    """Generate a stopped or failed reply again."""

    def begin(
        session: Session, user: User, chat_session: ChatSession
    ) -> tuple[ChatMessages, ChatMessages, Event]:
        return create_retry_message(
            session=session,
            user=user,
            chat_session=chat_session,
            failed_message_id=failed_message_id,
        )

    return stream_chat_generation(user_id=user_id, session_id=session_id, begin=begin)


async def stream_chat_generation(
    *, user_id: int, session_id: int, begin: BeginReply
) -> AsyncGenerator[str, None]:
    """
    Claim the chat session, write the reply's rows and stream the answer.

    All of it happens inside the running stream: if the client disconnects before
    the body starts, no claim is held and no reply is left `streaming`. Once `begin`
    returns, the try/finally below owns the claim and releases it on every path.
    """
    started = time.perf_counter()
    draft = ""
    original_draft = ""
    with Session(engine) as session:
        user = session.get(User, user_id)
        chat_session = session.get(ChatSession, session_id)
        if user is None or chat_session is None or chat_session.user_id != user_id:
            yield _start_failed_event("Chat session not found.")
            return
        try:
            user_message, assistant, cancellation = begin(session, user, chat_session)
        except HTTPException as exc:
            # A race the route's early check could not see; nothing was written
            yield _start_failed_event(str(exc.detail))
            return
        if user_message.id is None or assistant.id is None:
            raise RuntimeError("Reply rows were not persisted")
        user_message_id = user_message.id
        assistant_message_id = assistant.id
        try:
            yield encode_sse(
                "generation_started",
                {
                    "session_id": session_id,
                    "user_message": _message_payload(user_message),
                    "assistant_message": _message_payload(assistant),
                },
            )
            # Scan further back than the turns kept: failed drafts and retries are skipped
            recent_rows = session.exec(
                select(ChatMessages)
                .where(
                    ChatMessages.session_id == session_id,
                    col(ChatMessages.id) < user_message_id,
                )
                .order_by(col(ChatMessages.created_at).desc(), col(ChatMessages.id).desc())
                .limit(HISTORY_SCAN_LIMIT)
            ).all()
            history = build_conversation_history(list(reversed(recent_rows)))
            # Retrieval is synchronous (DB queries + embedding calls); keep it off the
            # event loop so other users' streams aren't stalled while it runs
            prepared = await asyncio.to_thread(
                _prepare_rag_in_own_session,
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
                # The draft and any repair pass both generated tokens for this reply
                assistant.tokens_used = llm.usage.generated_tokens
                assistant.response_time_ms = int((time.perf_counter() - started) * 1000)
                assistant.generation_status = ChatGenerationStatus.completed
                metadata = {
                    "repair_attempted": repair_attempted,
                    "validation": validation.reason or "valid",
                }
                if diagnostics_enabled:
                    metadata["retrieval"] = prepared.diagnostics
                # Keep reply_to / retry_of recorded when the message was created
                assistant.generation_metadata = {**(assistant.generation_metadata or {}), **metadata}
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
        except Exception:
            # The exception text can carry SQL, hostnames or paths; keep it server-side.
            logger.exception(
                "Streaming chat generation failed",
                extra={"session_id": session_id, "assistant_message_id": assistant_message_id},
            )
            assistant.content = draft or original_draft
            assistant.generation_status = ChatGenerationStatus.failed
            assistant.generation_error = GENERATION_FAILED_MESSAGE
            assistant.generation_completed_at = datetime.now(UTC)
            session.add(assistant)
            session.commit()
            yield encode_sse(
                "error",
                {
                    "code": "GENERATION_FAILED",
                    "message": GENERATION_FAILED_MESSAGE,
                    "retryable": True,
                    "assistant_message_id": assistant_message_id,
                },
            )
        finally:
            generation_coordinator.finish(session_id=session_id, message_id=assistant_message_id)
