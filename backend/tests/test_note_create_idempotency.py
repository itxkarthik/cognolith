"""A note create repeated with the same client request id makes one note."""

import threading

import pytest
from fastapi import HTTPException
from sqlmodel import Session, func, select

from app import crud
from app.core.database import engine
from app.models.note import Notes
from app.models.user import User, UserCreate
from app.schemas.note import NoteCreate
from app.services.note_service import create_note, soft_delete_note

KEY = "6f1c2a4e-offline-create"


@pytest.fixture
def user(session: Session) -> User:
    return crud.create_user(
        session=session,
        user_create=UserCreate(email="idempotent@example.com", password="secure-password"),
    )


def _create(
    session: Session, user: User, key: str | None = KEY, tag_ids: list[int] | None = None
) -> Notes:
    payload = NoteCreate(
        title="Offline", content="written offline", client_request_id=key, tag_ids=tag_ids or []
    )
    return create_note(session=session, current_user=user, payload=payload)


def _count(session: Session) -> int:
    session.expire_all()
    return session.exec(select(func.count()).select_from(Notes)).one()


def test_a_repeated_create_returns_the_first_note(session: Session, user: User) -> None:
    first = _create(session, user)
    again = _create(session, user)

    assert again.id == first.id
    assert _count(session) == 1


def test_creates_without_a_key_are_separate(session: Session, user: User) -> None:
    _create(session, user, key=None)
    _create(session, user, key=None)

    assert _count(session) == 2


def test_two_simultaneous_sends_make_one_note(session: Session, user: User) -> None:
    barrier = threading.Barrier(2)
    ids: list[int | None] = []

    def send() -> None:
        with Session(engine) as own_session:
            own_user = own_session.get(User, user.id)
            assert own_user is not None
            barrier.wait()
            ids.append(_create(own_session, own_user).id)

    threads = [threading.Thread(target=send) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(ids) == 2 and ids[0] == ids[1]
    assert _count(session) == 1


def test_a_replay_does_not_bring_back_a_deleted_note(session: Session, user: User) -> None:
    note = _create(session, user)
    assert note.id is not None
    soft_delete_note(session=session, current_user=user, note_id=note.id)

    with pytest.raises(HTTPException) as raised:
        _create(session, user)

    assert raised.value.status_code == 404


def test_a_rejected_create_leaves_no_note(session: Session, user: User) -> None:
    # Tags are saved with the note: an invalid one used to leave the note behind
    with pytest.raises(HTTPException):
        _create(session, user, tag_ids=[999_999])

    assert _count(session) == 0
