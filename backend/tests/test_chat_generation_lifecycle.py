"""A reply can't leak the session claim or stay "streaming" forever (issue #13)."""

import pytest
from fastapi import HTTPException
from sqlmodel import Session, col, select

from app import crud
from app.models.chat import ChatGenerationStatus, ChatMessages, ChatRole, ChatSession
from app.models.user import User, UserCreate
from app.services.chat_generation import (
    INTERRUPTED_MESSAGE,
    create_generation_messages,
    fail_interrupted_generations,
    generation_coordinator,
    stream_new_reply,
)


@pytest.fixture
def chat(session: Session) -> tuple[User, ChatSession]:
    user = crud.create_user(
        session=session,
        user_create=UserCreate(email="lifecycle@example.com", password="secure-password"),
    )
    chat_session = ChatSession(user_id=user.id, title="Lifecycle")
    session.add(chat_session)
    session.commit()
    session.refresh(chat_session)
    return user, chat_session


def _ids(chat: tuple[User, ChatSession]) -> tuple[int, int]:
    user, chat_session = chat
    assert user.id is not None and chat_session.id is not None
    return user.id, chat_session.id


def _messages(session: Session, chat_session_id: int) -> list[ChatMessages]:
    session.expire_all()
    return list(
        session.exec(select(ChatMessages).where(ChatMessages.session_id == chat_session_id))
    )


def test_losing_the_claim_race_writes_no_rows(
    session: Session, chat: tuple[User, ChatSession]
) -> None:
    user, chat_session = chat
    _, chat_session_id = _ids(chat)
    # Another reply claimed the session after the route's early check passed
    generation_coordinator.start(session_id=chat_session_id, message_id=999_999)
    try:
        with pytest.raises(HTTPException) as raised:
            create_generation_messages(
                session=session, user=user, chat_session=chat_session, content="Hello"
            )
    finally:
        generation_coordinator.finish(session_id=chat_session_id, message_id=999_999)

    assert raised.value.status_code == 409
    assert _messages(session, chat_session_id) == []  # no orphan question


@pytest.mark.asyncio
async def test_a_stream_that_never_starts_holds_nothing(
    session: Session, chat: tuple[User, ChatSession]
) -> None:
    user_id, chat_session_id = _ids(chat)

    # The client disconnects before the body is iterated
    stream = stream_new_reply(user_id=user_id, session_id=chat_session_id, content="Hello")
    await stream.aclose()

    assert not generation_coordinator.is_session_active(chat_session_id)
    assert _messages(session, chat_session_id) == []


@pytest.mark.asyncio
async def test_disconnecting_after_the_first_event_releases_the_claim(
    session: Session, chat: tuple[User, ChatSession]
) -> None:
    user_id, chat_session_id = _ids(chat)
    stream = stream_new_reply(user_id=user_id, session_id=chat_session_id, content="Hello")

    first = await anext(stream)
    assert first.startswith("event: generation_started")
    assert generation_coordinator.is_session_active(chat_session_id)
    await stream.aclose()

    assert not generation_coordinator.is_session_active(chat_session_id)
    reply = next(m for m in _messages(session, chat_session_id) if m.role == ChatRole.assistant)
    assert reply.generation_status == ChatGenerationStatus.cancelled


@pytest.mark.asyncio
async def test_a_race_lost_inside_the_stream_reports_an_error_event(
    session: Session, chat: tuple[User, ChatSession]
) -> None:
    user_id, chat_session_id = _ids(chat)
    generation_coordinator.start(session_id=chat_session_id, message_id=999_998)
    try:
        events = [
            event
            async for event in stream_new_reply(
                user_id=user_id, session_id=chat_session_id, content="Hello"
            )
        ]
    finally:
        generation_coordinator.finish(session_id=chat_session_id, message_id=999_998)

    assert len(events) == 1
    assert events[0].startswith("event: error")
    assert "GENERATION_NOT_STARTED" in events[0]
    assert _messages(session, chat_session_id) == []


def test_startup_fails_replies_left_streaming_by_a_crash(
    session: Session, chat: tuple[User, ChatSession]
) -> None:
    _, chat_session_id = _ids(chat)
    session.add_all(
        [
            ChatMessages(
                session_id=chat_session_id,
                role=ChatRole.assistant,
                content="half an ans",
                generation_status=ChatGenerationStatus.streaming,
            ),
            ChatMessages(
                session_id=chat_session_id,
                role=ChatRole.assistant,
                content="A full answer",
                generation_status=ChatGenerationStatus.completed,
            ),
        ]
    )
    session.commit()

    assert fail_interrupted_generations(session) == 1

    statuses = {
        message.content: (message.generation_status, message.generation_error)
        for message in _messages(session, chat_session_id)
    }
    assert statuses == {
        "half an ans": (ChatGenerationStatus.failed, INTERRUPTED_MESSAGE),
        "A full answer": (ChatGenerationStatus.completed, None),
    }
    remaining = session.exec(
        select(ChatMessages).where(
            col(ChatMessages.generation_status) == ChatGenerationStatus.streaming
        )
    ).all()
    assert remaining == []
