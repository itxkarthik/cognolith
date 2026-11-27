from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator, Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Event
from typing import Any

from fastapi import HTTPException
from sqlalchemy import cast, delete, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Session, col, select, update

from app.ai.grounding import build_grounding_repair_messages, validate_grounded_answer
from app.ai.llm import LLMConfig, LLMService, resolve_llm_config
from app.ai.rag import PreparedRAGResponse, finalize_prepared_answer, prepare_rag_pipeline
from app.core.database import engine
from app.models.chat import (
    ChatGenerationStatus,
    ChatMessages,
    ChatRole,
    ChatSession,
    chat_generation_claims,
)
from app.models.user import User, UserSettings
from app.services.chat_history import REPLY_TO_KEY, build_conversation_history
from app.services.generation_coordinator import CLAIM_LEASE_SECONDS, generation_coordinator
from app.services.workspace_indexer import workspace_indexer

logger = logging.getLogger(__name__)

GENERATION_FAILED_MESSAGE = "The AI response could not be completed."
INTERRUPTED_MESSAGE = "The reply was interrupted. Retry to generate it again."
# Recent messages read to build the history (several attempts can share one question)
HISTORY_SCAN_LIMIT = 40
# How often a streaming reply's draft is stored, so a crash keeps most of what was said
DRAFT_SAVE_INTERVAL_SECONDS = 1.0


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
    Blocking.
    """
    if generation_coordinator.is_session_active(session_id):
        raise HTTPException(status_code=409, detail="A reply is already being generated.")
    # No live claim: a reply still marked streaming here was left by a process that
    # stopped. Fail it now rather than at the next sweep, so it doesn't sit beside
    # the new reply looking unfinished.
    with Session(engine) as session:
        fail_interrupted_generations(session, chat_session_id=session_id)


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
    cancellation = _claim_and_commit(
        session=session, session_id=chat_session.id, reply=assistant, question=user_message
    )
    return user_message, assistant, cancellation


def ensure_retryable(
    *, session: Session, chat_session: ChatSession, failed_message_id: int
) -> ChatMessages:
    """Return the question a stopped or failed reply answered, or raise 409."""
    if chat_session.id is not None:
        # A reply left streaming by a process that died can be retried right away
        fail_interrupted_generations(session, chat_session_id=chat_session.id)
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


def _claim_and_commit(
    *,
    session: Session,
    session_id: int,
    reply: ChatMessages,
    question: ChatMessages | None = None,
) -> Event:
    """
    Claim the chat session for `reply` before its rows are committed: losing the race
    rolls them back instead of leaving an orphan question or a reply stuck streaming.

    Until this returns, the caller's stream hasn't taken ownership of the claim, so
    every failure after it is taken releases it here.
    """
    session.flush()  # assigns the reply's id, which the claim is keyed on
    reply_id = reply.id
    if reply_id is None:
        raise RuntimeError("Assistant message was not persisted")
    try:
        cancellation = generation_coordinator.start(session_id=session_id, message_id=reply_id)
    except HTTPException:
        session.rollback()
        raise
    committed = False
    try:
        session.commit()
        committed = True
        session.refresh(reply)
        if question is not None:
            session.refresh(question)
    except BaseException:
        session.rollback()
        if committed:
            _mark_reply_failed(reply_id)
        generation_coordinator.finish(session_id=session_id, message_id=reply_id)
        raise
    return cancellation


def _mark_reply_failed(reply_id: int) -> None:
    """Best effort, in its own session: a committed reply must not stay streaming."""
    try:
        with Session(engine) as session:
            session.exec(
                update(ChatMessages)
                .where(
                    col(ChatMessages.id) == reply_id,
                    col(ChatMessages.generation_status) == ChatGenerationStatus.streaming,
                )
                .values(
                    generation_status=ChatGenerationStatus.failed,
                    generation_error=GENERATION_FAILED_MESSAGE,
                    generation_completed_at=datetime.now(UTC),
                )
            )
            session.commit()
    except Exception:
        # The startup sweep fails it on the next restart
        logger.exception("Could not mark a reply failed", extra={"message_id": reply_id})


def fail_interrupted_generations(session: Session, *, chat_session_id: int | None = None) -> int:
    """
    Mark replies left `streaming` by a crash or restart as failed, so they can be
    retried. A reply whose claim is still live is being generated by some process
    and is left alone, so this is safe to run while other processes serve streams.
    """
    live_claim = (
        select(chat_generation_claims.c.session_id)
        .where(
            chat_generation_claims.c.message_id == ChatMessages.id,
            chat_generation_claims.c.heartbeat_at
            >= func.now() - timedelta(seconds=CLAIM_LEASE_SECONDS),
        )
        .exists()
    )
    statement = update(ChatMessages).where(
        col(ChatMessages.generation_status) == ChatGenerationStatus.streaming, ~live_claim
    )
    if chat_session_id is not None:
        statement = statement.where(col(ChatMessages.session_id) == chat_session_id)
    result = session.exec(
        statement.values(
            generation_status=ChatGenerationStatus.failed,
            generation_error=INTERRUPTED_MESSAGE,
            generation_completed_at=datetime.now(UTC),
        )
    )
    session.commit()
    return result.rowcount or 0


class AbandonedReplySweeper:
    """
    Fail replies left streaming by a process that stopped: at startup (this
    process's own, from before a crash) and every lease period after, since a claim
    only goes stale CLAIM_LEASE_SECONDS after its holder's last heartbeat.
    """

    def __init__(self, *, interval_seconds: float = CLAIM_LEASE_SECONDS) -> None:
        self.interval_seconds = interval_seconds
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="abandoned-reply-sweeper")

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    @staticmethod
    def sweep_once() -> int:
        with Session(engine) as session:
            failed = fail_interrupted_generations(session)
            delete_dead_claims(session)
            return failed

    async def _run(self) -> None:
        while True:
            try:
                failed = await asyncio.to_thread(self.sweep_once)
                if failed:
                    logger.info("Marked %s interrupted chat repl(ies) as failed", failed)
            except Exception:
                logger.exception("Failing interrupted chat replies did not complete")
            await asyncio.sleep(self.interval_seconds)


abandoned_reply_sweeper = AbandonedReplySweeper()


def delete_dead_claims(session: Session) -> int:
    """
    Delete claims nobody will release: their process stopped renewing them, or their
    reply finished over a lease period ago (a release that never ran). A live
    generation releases its claim right after the reply's final write.
    """
    lease = timedelta(seconds=CLAIM_LEASE_SECONDS)
    claims = chat_generation_claims
    finished_reply = (
        select(ChatMessages.id)
        .where(
            col(ChatMessages.id) == claims.c.message_id,
            col(ChatMessages.generation_status) != ChatGenerationStatus.streaming,
            col(ChatMessages.generation_completed_at) < func.now() - lease,
        )
        .exists()
    )
    result = session.exec(
        delete(claims).where((claims.c.heartbeat_at < func.now() - lease) | finished_reply)
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
        return prepare_rag_pipeline(
            session=rag_session,
            user_id=user_id,
            query=query,
            conversation_history=conversation_history,
        )


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


@dataclass(frozen=True, slots=True)
class _StartedReply:
    session_id: int
    question_id: int
    question: str
    reply_id: int
    cancellation: Event
    started_event: str


@dataclass(frozen=True, slots=True)
class _ReplyContext:
    history: list[dict[str, Any]]
    diagnostics_enabled: bool
    llm_config: LLMConfig


def _start_reply(*, user_id: int, session_id: int, begin: BeginReply) -> _StartedReply | str:
    """
    In a worker thread: claim the chat session and write the question and reply rows.
    Returns why nothing started instead, when nothing was claimed or written.
    """
    with Session(engine) as session:
        user = session.get(User, user_id)
        chat_session = session.get(ChatSession, session_id)
        if user is None or chat_session is None or chat_session.user_id != user_id:
            return "Chat session not found."
        try:
            question, reply, cancellation = begin(session, user, chat_session)
        except HTTPException as exc:
            # A race the route's early check could not see; nothing was written
            return str(exc.detail)
        if reply.id is None:
            # The claim is keyed on this id, so none can be held
            raise RuntimeError("Reply row was not persisted")
        try:
            if question.id is None:
                raise RuntimeError("Question row was not persisted")
            return _StartedReply(
                session_id=session_id,
                question_id=question.id,
                question=question.content,
                reply_id=reply.id,
                cancellation=cancellation,
                started_event=encode_sse(
                    "generation_started",
                    {
                        "session_id": session_id,
                        "user_message": _message_payload(question),
                        "assistant_message": _message_payload(reply),
                    },
                ),
            )
        except BaseException:
            _mark_reply_failed(reply.id)
            generation_coordinator.finish(session_id=session_id, message_id=reply.id)
            raise


def _release_unstreamed_reply(start: asyncio.Future[_StartedReply | str]) -> None:
    """
    The client left while the reply was being started. Once the start finishes, stop
    the reply it wrote and release its claim, since no stream will.
    """
    if start.cancelled() or start.exception() is not None:
        return
    started = start.result()
    if isinstance(started, str):
        return
    started.cancellation.set()

    def release() -> None:
        try:
            _finish_reply(
                started.reply_id,
                only_if_streaming=True,
                generation_status=ChatGenerationStatus.cancelled,
                generation_completed_at=datetime.now(UTC),
            )
        finally:
            generation_coordinator.finish(
                session_id=started.session_id, message_id=started.reply_id
            )

    asyncio.get_running_loop().run_in_executor(None, release)


def _load_reply_context(*, user_id: int, session_id: int, question_id: int) -> _ReplyContext:
    with Session(engine) as session:
        # Scan further back than the turns kept: failed drafts and retries are skipped
        recent_rows = session.exec(
            select(ChatMessages)
            .where(ChatMessages.session_id == session_id, col(ChatMessages.id) < question_id)
            .order_by(col(ChatMessages.created_at).desc(), col(ChatMessages.id).desc())
            .limit(HISTORY_SCAN_LIMIT)
        ).all()
        preferences = session.get(UserSettings, user_id)
        return _ReplyContext(
            history=build_conversation_history(list(reversed(recent_rows))),
            diagnostics_enabled=bool(preferences and preferences.rag_diagnostics_enabled),
            llm_config=resolve_llm_config(session=session, user_id=user_id),
        )


def _save_draft(reply_id: int, content: str) -> None:
    """
    Store the reply so far. Only a reply still streaming is touched, so a save that
    lands after the final write (they run in different sessions) changes nothing.
    """
    try:
        with Session(engine) as session:
            session.exec(
                update(ChatMessages)
                .where(
                    col(ChatMessages.id) == reply_id,
                    col(ChatMessages.generation_status) == ChatGenerationStatus.streaming,
                )
                .values(content=content)
            )
            session.commit()
    except Exception:
        # The next save, or the final write, stores it
        logger.exception("Could not save a reply draft", extra={"message_id": reply_id})


def _finish_reply(reply_id: int, *, only_if_streaming: bool, **values: Any) -> dict[str, Any]:
    """Write a reply's final state and return it as sent to the client."""
    with Session(engine) as session:
        statement = update(ChatMessages).where(col(ChatMessages.id) == reply_id)
        if only_if_streaming:
            # Leaves a reply another path already finished as it is
            statement = statement.where(
                col(ChatMessages.generation_status) == ChatGenerationStatus.streaming
            )
        session.exec(statement.values(**values))
        session.commit()
        reply = session.get(ChatMessages, reply_id)
        if reply is None:
            raise RuntimeError("Reply row disappeared")
        return _message_payload(reply)


async def stream_chat_generation(
    *, user_id: int, session_id: int, begin: BeginReply
) -> AsyncGenerator[str, None]:
    """
    Claim the chat session, write the reply's rows and stream the answer.

    All of it happens inside the running stream: if the client disconnects before
    the body starts, no claim is held and no reply is left `streaming`. Once the
    start returns, the try/finally below owns the claim and releases it on every path.

    Database work runs in worker threads, each with its own session, so a slow query
    or commit never holds up the event loop and the other streams on it. The one
    exception is the write after a cancellation, which must be synchronous.
    """
    started_at = time.perf_counter()
    start = asyncio.ensure_future(
        asyncio.to_thread(_start_reply, user_id=user_id, session_id=session_id, begin=begin)
    )
    try:
        # Shielded: a client leaving mid-start must not lose a claim already taken
        started = await asyncio.shield(start)
    except asyncio.CancelledError:
        start.add_done_callback(_release_unstreamed_reply)
        raise
    if isinstance(started, str):
        yield _start_failed_event(started)
        return

    reply_id = started.reply_id
    cancellation = started.cancellation
    draft = ""
    original_draft = ""
    draft_save: asyncio.Future[None] | None = None
    last_save = time.monotonic()
    stopping = False
    released = False

    async def release_claim() -> None:
        # Before the final event: a client may send its next message as soon as it
        # sees it, and must not find the session still claimed
        nonlocal released
        # Shielded: if the client leaves now, a cancelled to_thread() call that no
        # thread has started yet would be dropped, and the session stay claimed.
        # `released` is set only once it's done; otherwise `finally` releases again.
        await asyncio.shield(
            asyncio.to_thread(
                generation_coordinator.finish, session_id=session_id, message_id=reply_id
            )
        )
        released = True
    try:
        yield started.started_event
        context = await asyncio.to_thread(
            _load_reply_context,
            user_id=user_id,
            session_id=session_id,
            question_id=started.question_id,
        )
        prepared = await asyncio.to_thread(
            _prepare_rag_in_own_session,
            user_id=user_id,
            query=started.question,
            conversation_history=context.history,
        )
        yield encode_sse(
            "retrieval_complete",
            {
                "message_id": reply_id,
                "diagnostics": prepared.diagnostics if context.diagnostics_enabled else None,
            },
        )
        llm = LLMService(session=None, user_id=user_id, config=context.llm_config)
        async for delta in llm.stream_response(messages=prepared.messages):
            if cancellation.is_set():
                break
            draft += delta
            yield encode_sse("token", {"message_id": reply_id, "delta": delta})
            now = time.monotonic()
            # One save in flight at most; the next one carries everything since
            if now - last_save >= DRAFT_SAVE_INTERVAL_SECONDS and (
                draft_save is None or draft_save.done()
            ):
                draft_save = asyncio.ensure_future(asyncio.to_thread(_save_draft, reply_id, draft))
                last_save = now

        if cancellation.is_set():
            message = await asyncio.to_thread(
                _finish_reply,
                reply_id,
                only_if_streaming=True,
                content=draft,
                generation_status=ChatGenerationStatus.cancelled,
                generation_completed_at=datetime.now(UTC),
            )
            await release_claim()
            yield encode_sse("cancelled", {"message": message})
            return

        original_draft = draft
        valid_ids = {source.citation_id for source in prepared.context_sources}
        validation = validate_grounded_answer(draft, valid_citation_ids=valid_ids)
        repair_attempted = prepared.grounded and not validation.is_valid
        if repair_attempted:
            yield encode_sse(
                "answer_reset", {"message_id": reply_id, "reason": "grounding_repair"}
            )
            draft = ""
            repair_messages = build_grounding_repair_messages(
                messages=prepared.messages, draft=original_draft, valid_citation_ids=valid_ids
            )
            try:
                async for delta in llm.stream_response(messages=repair_messages):
                    if cancellation.is_set():
                        break
                    draft += delta
                    yield encode_sse("token", {"message_id": reply_id, "delta": delta})
            except Exception:
                draft = original_draft

        if cancellation.is_set():
            values: dict[str, Any] = {
                "content": draft,
                "generation_status": ChatGenerationStatus.cancelled,
            }
        else:
            final_answer, sources = finalize_prepared_answer(draft, prepared=prepared)
            metadata: dict[str, Any] = {
                "repair_attempted": repair_attempted,
                "validation": validation.reason or "valid",
            }
            if context.diagnostics_enabled:
                metadata["retrieval"] = prepared.diagnostics
            values = {
                "content": final_answer,
                "sources": sources,
                # The draft and any repair pass both generated tokens for this reply
                "tokens_used": llm.usage.generated_tokens,
                "response_time_ms": int((time.perf_counter() - started_at) * 1000),
                "generation_status": ChatGenerationStatus.completed,
                # Keeps reply_to / retry_of, recorded when the message was created
                "generation_metadata": func.coalesce(
                    ChatMessages.generation_metadata, cast({}, JSONB)
                ).op("||")(cast(metadata, JSONB)),
            }
        message = await asyncio.to_thread(
            _finish_reply,
            reply_id,
            only_if_streaming=False,
            generation_completed_at=datetime.now(UTC),
            **values,
        )
        workspace_indexer.mark_dirty(user_id)
        await release_claim()
        if message["generation_status"] == ChatGenerationStatus.cancelled:
            yield encode_sse("cancelled", {"message": message})
        else:
            yield encode_sse(
                "sources", {"message_id": reply_id, "sources": message["sources"] or {}}
            )
            yield encode_sse("completed", {"message": message})
    except (asyncio.CancelledError, GeneratorExit):
        stopping = True
        cancellation.set()
        # Synchronous: in a cancelled stream every await is cancelled again. Guarded,
        # so a final write already made (or still committing) is kept.
        _finish_reply(
            reply_id,
            only_if_streaming=True,
            content=draft or original_draft,
            generation_status=ChatGenerationStatus.cancelled,
            generation_completed_at=datetime.now(UTC),
        )
        raise
    except Exception:
        # The exception text can carry SQL, hostnames or paths; keep it server-side.
        logger.exception(
            "Streaming chat generation failed",
            extra={"session_id": session_id, "assistant_message_id": reply_id},
        )
        await asyncio.to_thread(
            _finish_reply,
            reply_id,
            only_if_streaming=True,
            content=draft or original_draft,
            generation_status=ChatGenerationStatus.failed,
            generation_error=GENERATION_FAILED_MESSAGE,
            generation_completed_at=datetime.now(UTC),
        )
        await release_claim()
        yield encode_sse(
            "error",
            {
                "code": "GENERATION_FAILED",
                "message": GENERATION_FAILED_MESSAGE,
                "retryable": True,
                "assistant_message_id": reply_id,
            },
        )
    finally:
        if stopping and not released:
            # Synchronous for the same reason as the cancelled write above
            generation_coordinator.finish(session_id=session_id, message_id=reply_id)
        elif not released:
            await release_claim()
