"""The chat session list returns summaries, not every message (issue #26)."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import event
from sqlmodel import Session

from app import crud
from app.models.chat import ChatMessages, ChatRole, ChatSession
from app.models.user import User, UserCreate
from app.services.chat_service import LAST_MESSAGE_PREVIEW_CHARS, list_chat_sessions

START = datetime(2026, 1, 1, tzinfo=UTC)


def _user(session: Session, email: str = "list@example.com") -> User:
    return crud.create_user(
        session=session, user_create=UserCreate(email=email, password="secure-password")
    )


def _chat(session: Session, user: User, title: str, contents: list[str], minutes: int) -> int:
    chat = ChatSession(
        user_id=user.id, title=title, last_message_at=START + timedelta(minutes=minutes)
    )
    session.add(chat)
    session.flush()
    for offset, content in enumerate(contents):
        session.add(
            ChatMessages(
                session_id=chat.id,
                role=ChatRole.user if offset % 2 == 0 else ChatRole.assistant,
                content=content,
                created_at=START + timedelta(minutes=minutes, seconds=offset),
            )
        )
    session.commit()
    assert chat.id is not None
    return chat.id


def test_each_session_carries_its_count_and_last_message(session: Session) -> None:
    user = _user(session)
    busy = _chat(session, user, "Busy", ["Question", "Answer", "Follow-up", ""], minutes=2)
    empty = _chat(session, user, "Empty", [], minutes=1)

    summaries, total = list_chat_sessions(session=session, current_user=user)

    assert total == 2
    assert [summary.id for summary in summaries] == [busy, empty]
    assert summaries[0].message_count == 4
    # The empty reply (still streaming) is skipped for the preview
    assert summaries[0].last_message is not None
    assert summaries[0].last_message.content == "Follow-up"
    assert summaries[0].last_message.role == "user"
    assert summaries[1].message_count == 0
    assert summaries[1].last_message is None
    assert "messages" not in summaries[0].model_dump()


def test_the_preview_is_cut_in_the_database(session: Session) -> None:
    user = _user(session)
    _chat(session, user, "Long", ["x" * 10_000], minutes=0)

    [summary], _ = list_chat_sessions(session=session, current_user=user)

    assert summary.last_message is not None
    assert len(summary.last_message.content) == LAST_MESSAGE_PREVIEW_CHARS


def test_only_the_users_own_sessions_are_listed(session: Session) -> None:
    owner = _user(session)
    other = _user(session, "other@example.com")
    _chat(session, other, "Not yours", ["secret"], minutes=0)
    mine = _chat(session, owner, "Mine", ["hello"], minutes=0)

    summaries, total = list_chat_sessions(session=session, current_user=owner)

    assert total == 1
    assert [summary.id for summary in summaries] == [mine]


def test_a_page_is_two_queries_however_many_messages(session: Session) -> None:
    user = _user(session)
    for index in range(10):
        _chat(session, user, f"Chat {index}", ["message"] * 30, minutes=index)

    assert user.id is not None  # loaded before counting
    statements: list[str] = []

    def record(*args: object) -> None:
        statements.append(str(args[2]))

    bind = session.get_bind()
    event.listen(bind, "before_cursor_execute", record)
    try:
        summaries, _ = list_chat_sessions(session=session, current_user=user, limit=5)
    finally:
        event.remove(bind, "before_cursor_execute", record)

    assert len(summaries) == 5
    # One count, one page; no message rows are loaded
    assert len(statements) == 2
    assert all("chat_messages.sources" not in statement for statement in statements)
