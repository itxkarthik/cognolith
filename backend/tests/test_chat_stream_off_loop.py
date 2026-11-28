"""A streamed reply keeps its database work off the event loop (issue #25)."""

import asyncio
import threading
import time
from collections.abc import AsyncIterator, Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from sqlalchemy import event
from sqlmodel import Session, select

from app import crud
from app.ai.rag import PreparedRAGResponse
from app.core.database import engine
from app.models.chat import ChatGenerationStatus, ChatMessages, ChatRole, ChatSession
from app.models.user import UserCreate
from app.services import chat_generation
from app.services.chat_generation import generation_coordinator, stream_new_reply
from app.services.chat_history import REPLY_TO_KEY
from app.services.workspace_indexer import workspace_indexer

TOKENS = ["The ", "answer ", "is ", "forty-two."]


@pytest.fixture
def chat(session: Session) -> tuple[int, int]:
    user = crud.create_user(
        session=session,
        user_create=UserCreate(email="offloop@example.com", password="secure-password"),
    )
    chat_session = ChatSession(user_id=user.id, title="Off the loop")
    session.add(chat_session)
    session.commit()
    assert user.id is not None and chat_session.id is not None
    return user.id, chat_session.id


class FakeLLM:
    """Streams TOKENS, pausing between them so draft saves can run."""

    def __init__(self, **_: object) -> None:
        self.usage = type("Usage", (), {"generated_tokens": len(TOKENS)})()

    async def stream_response(self, *, messages: object) -> AsyncIterator[str]:
        del messages
        for token in TOKENS:
            await asyncio.sleep(0.02)
            yield token


def _prepared(**_: object) -> PreparedRAGResponse:
    return PreparedRAGResponse(
        messages=[{"role": "user", "content": "q"}],
        context_sources=[],
        context_chunks=[],
        grounded=False,
        diagnostics={},
    )


@pytest.fixture
def fake_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(chat_generation, "LLMService", FakeLLM)
    monkeypatch.setattr(chat_generation, "_prepare_rag_in_own_session", _prepared)


@pytest.fixture
def slow_database() -> Iterator[None]:
    """Every statement takes 50 ms, like a loaded database."""

    def stall(*_: object) -> None:
        time.sleep(0.05)

    event.listen(engine, "before_cursor_execute", stall)
    yield
    event.remove(engine, "before_cursor_execute", stall)


def _reply(session: Session, chat_session_id: int) -> ChatMessages:
    session.expire_all()
    return session.exec(
        select(ChatMessages).where(
            ChatMessages.session_id == chat_session_id, ChatMessages.role == ChatRole.assistant
        )
    ).one()


async def _collect(stream: AsyncIterator[str]) -> list[str]:
    return [item async for item in stream]


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_model", "slow_database")
async def test_a_slow_database_does_not_stall_the_event_loop(chat: tuple[int, int]) -> None:
    user_id, chat_session_id = chat
    gaps: list[float] = []
    done = False

    async def heartbeat() -> None:
        last = time.perf_counter()
        while not done:
            await asyncio.sleep(0.005)
            now = time.perf_counter()
            gaps.append(now - last)
            last = now

    beating = asyncio.create_task(heartbeat())
    events = await _collect(
        stream_new_reply(user_id=user_id, session_id=chat_session_id, content="Question")
    )
    done = True
    await beating

    assert events[-1].startswith("event: completed")
    # Each statement stalls 50 ms; on the loop, other streams would wait that long
    assert max(gaps) < 0.04


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_model")
async def test_a_completed_reply_keeps_its_metadata_and_text(
    session: Session, chat: tuple[int, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id, chat_session_id = chat
    monkeypatch.setattr(chat_generation, "DRAFT_SAVE_INTERVAL_SECONDS", 0.0)

    events = await _collect(
        stream_new_reply(user_id=user_id, session_id=chat_session_id, content="Question")
    )

    assert events[-1].startswith("event: completed")
    await asyncio.sleep(0.1)  # any draft save still in flight lands now
    reply = _reply(session, chat_session_id)
    assert reply.content == "".join(TOKENS)
    assert reply.generation_status == ChatGenerationStatus.completed
    assert reply.tokens_used == len(TOKENS)
    metadata = reply.generation_metadata or {}
    # Recorded at creation, kept by the final write
    assert REPLY_TO_KEY in metadata
    assert metadata["validation"] == "valid"
    assert not generation_coordinator.is_session_active(chat_session_id)


@pytest.mark.asyncio
async def test_drafts_are_saved_while_the_reply_streams(
    session: Session, chat: tuple[int, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id, chat_session_id = chat
    monkeypatch.setattr(chat_generation, "DRAFT_SAVE_INTERVAL_SECONDS", 0.0)
    monkeypatch.setattr(chat_generation, "_prepare_rag_in_own_session", _prepared)
    paused = asyncio.Event()
    resume = asyncio.Event()

    class PausingLLM(FakeLLM):
        async def stream_response(self, *, messages: object) -> AsyncIterator[str]:
            del messages
            yield "Partial "
            yield "text"
            paused.set()
            await resume.wait()
            yield " done."

    monkeypatch.setattr(chat_generation, "LLMService", PausingLLM)
    running = asyncio.create_task(
        _collect(stream_new_reply(user_id=user_id, session_id=chat_session_id, content="Q"))
    )
    await paused.wait()
    await asyncio.sleep(0.2)  # the save started on the last token completes

    assert _reply(session, chat_session_id).content.startswith("Partial")
    resume.set()
    await running
    assert _reply(session, chat_session_id).content == "Partial text done."


def test_a_late_draft_save_cannot_undo_the_final_write(
    session: Session, chat: tuple[int, int]
) -> None:
    _, chat_session_id = chat
    reply = ChatMessages(
        session_id=chat_session_id,
        role=ChatRole.assistant,
        content="",
        generation_status=ChatGenerationStatus.streaming,
    )
    session.add(reply)
    session.commit()
    assert reply.id is not None

    chat_generation._finish_reply(  # pyright: ignore[reportPrivateUsage]
        reply.id,
        only_if_streaming=False,
        content="Final answer",
        generation_status=ChatGenerationStatus.completed,
    )
    chat_generation._save_draft(reply.id, "Final ans")  # pyright: ignore[reportPrivateUsage]

    stored = _reply(session, chat_session_id)
    assert (stored.content, stored.generation_status) == (
        "Final answer",
        ChatGenerationStatus.completed,
    )


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_model")
async def test_leaving_while_the_reply_is_starting_releases_its_claim(
    session: Session, chat: tuple[int, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id, chat_session_id = chat
    entered = threading.Event()
    proceed = threading.Event()
    original_begin = chat_generation.create_generation_messages

    def slow_begin(**kwargs: Any) -> Any:
        entered.set()
        proceed.wait(timeout=5)
        return original_begin(**kwargs)

    monkeypatch.setattr(chat_generation, "create_generation_messages", slow_begin)
    stream = stream_new_reply(user_id=user_id, session_id=chat_session_id, content="Q")
    first = asyncio.create_task(anext(stream))
    await asyncio.to_thread(entered.wait, 5)

    first.cancel()  # the client leaves while the claim is being taken
    with pytest.raises(asyncio.CancelledError):
        await first
    proceed.set()

    for _ in range(100):
        await asyncio.sleep(0.02)
        if not generation_coordinator.is_session_active(chat_session_id):
            break
    assert not generation_coordinator.is_session_active(chat_session_id)
    assert _reply(session, chat_session_id).generation_status == ChatGenerationStatus.cancelled


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_model")
async def test_the_session_is_free_when_the_client_sees_the_final_event(
    chat: tuple[int, int],
) -> None:
    user_id, chat_session_id = chat
    stream = stream_new_reply(user_id=user_id, session_id=chat_session_id, content="Question")

    async for sse in stream:
        if sse.startswith("event: completed"):
            # The client may send its next message right away
            busy = await asyncio.to_thread(
                generation_coordinator.is_session_active, chat_session_id
            )
            assert not busy
            break
    else:
        pytest.fail("the stream never completed")
    await stream.aclose()


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_model")
async def test_a_client_leaving_while_the_release_waits_for_a_thread_still_frees_the_session(
    chat: tuple[int, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id, chat_session_id = chat
    # One worker thread, busy from right after the final write: the release that
    # follows waits in the queue, where cancelling the stream would drop it
    loop = asyncio.get_running_loop()
    executor = ThreadPoolExecutor(max_workers=1)
    loop.set_default_executor(executor)
    final_written = threading.Event()
    gate = threading.Event()
    original_finish_reply = chat_generation._finish_reply  # pyright: ignore[reportPrivateUsage]

    def finish_reply_then_hold_the_thread(*args: Any, **kwargs: Any) -> Any:
        result = original_finish_reply(*args, **kwargs)
        if kwargs.get("generation_status") == ChatGenerationStatus.completed:
            # Queued before the stream resumes, so its release queues behind it
            loop.call_soon_threadsafe(loop.run_in_executor, None, gate.wait, 5)
            final_written.set()
        return result

    monkeypatch.setattr(chat_generation, "_finish_reply", finish_reply_then_hold_the_thread)
    consuming = asyncio.create_task(
        _collect(stream_new_reply(user_id=user_id, session_id=chat_session_id, content="Q"))
    )
    for _ in range(500):
        if final_written.is_set():
            break
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.05)  # the stream moves on to the release, which queues

    consuming.cancel()  # the client disconnects
    with pytest.raises(asyncio.CancelledError):
        await consuming
    gate.set()

    try:
        for _ in range(100):
            if not generation_coordinator.is_session_active(chat_session_id):
                break
            await asyncio.sleep(0.02)
        assert not generation_coordinator.is_session_active(chat_session_id)
    finally:
        executor.shutdown(wait=True)


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_model")
async def test_a_stopped_reply_is_queued_for_indexing(chat: tuple[int, int]) -> None:
    user_id, chat_session_id = chat
    stream = stream_new_reply(user_id=user_id, session_id=chat_session_id, content="Q")

    async for sse in stream:
        if sse.startswith("event: token"):
            break  # the client leaves after the first token
    # Starting the reply committed the session, which marked the owner already
    with workspace_indexer._lock:  # pyright: ignore[reportPrivateUsage]
        workspace_indexer._due.clear()  # pyright: ignore[reportPrivateUsage]
    await stream.aclose()

    assert user_id in workspace_indexer.pending()
