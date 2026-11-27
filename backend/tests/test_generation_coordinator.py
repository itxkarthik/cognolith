"""Reply claims and cancel requests hold across backend processes (issue #29).

Two coordinator instances stand in for two processes sharing the database.
"""

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlmodel import Session

from app.core.database import engine
from app.models.chat import ChatGenerationStatus, ChatMessages, ChatRole, ChatSession
from app.models.user import User
from app.services import chat_generation
from app.services.chat_generation import (
    AbandonedReplySweeper,
    delete_dead_claims,
    fail_interrupted_generations,
)
from app.services.generation_coordinator import PostgresGenerationCoordinator


@pytest.fixture
def processes(session: Session) -> Iterator[tuple[PostgresGenerationCoordinator, ...]]:
    del session  # creates the tables
    # A long heartbeat: the tests renew by hand
    yield tuple(PostgresGenerationCoordinator(heartbeat_seconds=3600) for _ in range(2))


def _age_claims(seconds: int) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE chat_generation_claims "
                "SET heartbeat_at = heartbeat_at - make_interval(secs => :seconds)"
            ),
            {"seconds": seconds},
        )


def test_one_reply_at_a_time_per_session_across_processes(processes) -> None:
    first, second = processes
    first.start(session_id=1, message_id=10)

    with pytest.raises(HTTPException) as raised:
        second.start(session_id=1, message_id=11)
    assert raised.value.status_code == 409
    assert second.is_session_active(1)

    first.finish(session_id=1, message_id=10)
    second.start(session_id=1, message_id=11)


def test_non_streaming_reservation_blocks_a_streamed_reply(processes) -> None:
    first, second = processes

    with first.exclusive(session_id=3):
        assert second.is_session_active(3)
        with pytest.raises(HTTPException):
            second.start(session_id=3, message_id=30)

    assert not second.is_session_active(3)


def test_a_cancel_received_by_another_process_stops_the_reply(processes) -> None:
    generating, receiving = processes
    cancellation = generating.start(session_id=5, message_id=50)

    assert receiving.cancel(50) is True
    assert not cancellation.is_set()  # not yet seen by the generating process
    generating.renew()
    assert cancellation.is_set()
    assert receiving.cancel(999) is False


def test_finishing_another_reply_does_not_release_the_session(processes) -> None:
    first, _ = processes
    first.start(session_id=9, message_id=90)

    first.finish(session_id=9, message_id=91)

    assert first.is_session_active(9)


def test_a_dead_processs_claim_can_be_taken_over(processes) -> None:
    dead, alive = processes
    abandoned = dead.start(session_id=7, message_id=70)
    _age_claims(3600)  # its heartbeat stopped

    assert not alive.is_session_active(7)
    alive.start(session_id=7, message_id=71)

    # Should the first process come back, it learns its reply was superseded
    dead.renew()
    assert abandoned.is_set()
    assert alive.is_session_active(7)


def test_renewal_keeps_a_long_reply_claimed(processes) -> None:
    first, second = processes
    first.start(session_id=8, message_id=80)
    _age_claims(25)
    first.renew()
    _age_claims(10)  # 35 s since the claim, 10 s since the renewal

    with pytest.raises(HTTPException):
        second.start(session_id=8, message_id=81)


def test_the_sweep_fails_only_replies_without_a_live_claim(session: Session, processes) -> None:
    first, _ = processes
    user = User(email="sweep@example.com", hashed_password="unused", is_verified=True)
    session.add(user)
    session.commit()
    chats = [ChatSession(user_id=user.id, title=title) for title in ("live", "dead")]
    session.add_all(chats)
    session.commit()
    replies = [
        ChatMessages(
            session_id=chat.id,
            role=ChatRole.assistant,
            content="",
            generation_status=ChatGenerationStatus.streaming,
        )
        for chat in chats
    ]
    session.add_all(replies)
    session.commit()
    live, dead = replies
    assert live.id is not None and chats[0].id is not None
    first.start(session_id=chats[0].id, message_id=live.id)

    assert fail_interrupted_generations(session) == 1

    session.expire_all()
    assert session.get(ChatMessages, live.id).generation_status == ChatGenerationStatus.streaming  # pyright: ignore[reportOptionalMemberAccess]
    assert session.get(ChatMessages, dead.id).generation_status == ChatGenerationStatus.failed  # pyright: ignore[reportOptionalMemberAccess]


def test_the_sweeper_fails_a_crashed_processs_reply_once_its_claim_is_stale(
    session: Session, processes
) -> None:
    crashed, _ = processes
    user = User(email="crash@example.com", hashed_password="unused", is_verified=True)
    session.add(user)
    session.commit()
    chat = ChatSession(user_id=user.id, title="crash")
    session.add(chat)
    session.commit()
    reply = ChatMessages(
        session_id=chat.id,
        role=ChatRole.assistant,
        content="",
        generation_status=ChatGenerationStatus.streaming,
    )
    session.add(reply)
    session.commit()
    assert chat.id is not None and reply.id is not None
    crashed.start(session_id=chat.id, message_id=reply.id)
    sweeper = AbandonedReplySweeper(interval_seconds=0.02)

    async def sweep_for(seconds: float) -> None:
        await sweeper.start()
        await asyncio.sleep(seconds)
        await sweeper.stop()

    asyncio.run(sweep_for(0.1))
    session.expire_all()
    assert session.get(ChatMessages, reply.id).generation_status == ChatGenerationStatus.streaming  # pyright: ignore[reportOptionalMemberAccess]

    _age_claims(3600)  # the process died: no more heartbeats
    asyncio.run(sweep_for(0.1))
    session.expire_all()
    assert session.get(ChatMessages, reply.id).generation_status == ChatGenerationStatus.failed  # pyright: ignore[reportOptionalMemberAccess]


def test_claims_nobody_will_release_are_deleted(session: Session, processes) -> None:
    holder, _ = processes
    user = User(email="leak@example.com", hashed_password="unused", is_verified=True)
    session.add(user)
    session.commit()
    chats = [ChatSession(user_id=user.id, title=title) for title in ("live", "leaked", "dead")]
    session.add_all(chats)
    session.commit()
    replies = [
        ChatMessages(
            session_id=chat.id,
            role=ChatRole.assistant,
            content="",
            generation_status=status,
            generation_completed_at=completed,
        )
        for chat, status, completed in (
            (chats[0], ChatGenerationStatus.streaming, None),
            # Finished a minute ago, yet still claimed: its release never ran
            (chats[1], ChatGenerationStatus.completed, datetime.now(UTC) - timedelta(minutes=1)),
            (chats[2], ChatGenerationStatus.streaming, None),
        )
    ]
    session.add_all(replies)
    session.commit()
    for chat, reply in zip(chats, replies, strict=True):
        assert chat.id is not None and reply.id is not None
        holder.start(session_id=chat.id, message_id=reply.id)
    with engine.begin() as connection:  # the third's process died
        connection.execute(
            text(
                "UPDATE chat_generation_claims SET heartbeat_at = now() - interval '1 hour' "
                "WHERE session_id = :id"
            ),
            {"id": chats[2].id},
        )

    assert delete_dead_claims(session) == 2

    live, leaked, dead = (chat.id for chat in chats)
    assert holder.is_session_active(live)  # pyright: ignore[reportArgumentType]
    assert not holder.is_session_active(leaked)  # pyright: ignore[reportArgumentType]
    assert not holder.is_session_active(dead)  # pyright: ignore[reportArgumentType]
    # The holder stops renewing claims that are gone
    holder.renew()
    assert set(holder._held) == {live}  # pyright: ignore[reportPrivateUsage]


def test_sending_into_a_freed_session_fails_its_abandoned_reply_at_once(
    session: Session, processes, monkeypatch: pytest.MonkeyPatch
) -> None:
    crashed, _ = processes
    user = User(email="abandoned@example.com", hashed_password="unused", is_verified=True)
    session.add(user)
    session.commit()
    chat = ChatSession(user_id=user.id, title="abandoned")
    session.add(chat)
    session.commit()
    reply = ChatMessages(
        session_id=chat.id,
        role=ChatRole.assistant,
        content="",
        generation_status=ChatGenerationStatus.streaming,
    )
    session.add(reply)
    session.commit()
    assert chat.id is not None and reply.id is not None
    crashed.start(session_id=chat.id, message_id=reply.id)
    monkeypatch.setattr(chat_generation, "generation_coordinator", crashed)

    with pytest.raises(HTTPException):  # still claimed
        chat_generation.ensure_no_active_generation(chat.id)
    _age_claims(3600)  # its process died
    chat_generation.ensure_no_active_generation(chat.id)

    session.expire_all()
    assert session.get(ChatMessages, reply.id).generation_status == ChatGenerationStatus.failed  # pyright: ignore[reportOptionalMemberAccess]
