"""A save based on a stale revision is refused instead of overwriting (issue #18)."""

import threading

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app import crud
from app.core.config import settings
from app.core.database import engine
from app.core.exceptions import ConflictError
from app.main import app
from app.models.note import Notes
from app.models.user import User, UserCreate
from app.schemas.note import NoteUpdate
from app.services.note_service import update_note

API = settings.API_V1_STR
EMAIL = "conflicts@example.com"
PASSWORD = "secure-password"


@pytest.fixture
def user(session: Session) -> User:
    return crud.create_user(session=session, user_create=UserCreate(email=EMAIL, password=PASSWORD))


@pytest.fixture
def note(session: Session, user: User) -> Notes:
    note = Notes(user_id=user.id, title="Shared", content="original")
    session.add(note)
    session.commit()
    session.refresh(note)
    return note


def _save(session: Session, user: User, note: Notes, content: str, revision: int | None) -> Notes:
    assert note.id is not None
    return update_note(
        session=session,
        current_user=user,
        note_id=note.id,
        payload=NoteUpdate(content=content, expected_revision=revision),
    )


def test_every_write_bumps_the_revision(session: Session, user: User, note: Notes) -> None:
    assert note.revision == 1

    assert _save(session, user, note, "one", 1).revision == 2
    assert _save(session, user, note, "two", None).revision == 3


def test_a_stale_save_is_refused_and_keeps_the_newer_content(
    session: Session, user: User, note: Notes
) -> None:
    _save(session, user, note, "from tab A", 1)

    with pytest.raises(ConflictError):
        _save(session, user, note, "from tab B", 1)

    session.expire_all()
    current = session.get(Notes, note.id)
    assert current is not None
    assert (current.content, current.revision) == ("from tab A", 2)


def test_overwriting_after_a_conflict_uses_the_server_revision(
    session: Session, user: User, note: Notes
) -> None:
    _save(session, user, note, "from tab A", 1)

    overwritten = _save(session, user, note, "from tab B", 2)

    assert (overwritten.content, overwritten.revision) == ("from tab B", 3)


def test_two_saves_from_the_same_revision_cannot_both_win(user: User, note: Notes) -> None:
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def save(content: str) -> None:
        with Session(engine) as own_session:
            own_user = own_session.get(User, user.id)
            assert own_user is not None
            barrier.wait()
            try:
                _save(own_session, own_user, note, content, 1)
                outcomes.append("saved")
            except ConflictError:
                outcomes.append("conflict")

    threads = [threading.Thread(target=save, args=(text,)) for text in ("A", "B")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(outcomes) == ["conflict", "saved"]


def test_the_route_returns_409_with_a_conflict_error(user: User, note: Notes) -> None:
    browser = TestClient(app)
    login = browser.post(
        f"{API}/login/access-token", data={"username": EMAIL, "password": PASSWORD}
    )
    assert login.status_code == 200
    headers = {settings.CSRF_HEADER_NAME: browser.cookies.get(settings.CSRF_COOKIE_NAME) or ""}

    first = browser.patch(
        f"{API}/notes/{note.id}", json={"content": "A", "expected_revision": 1}, headers=headers
    )
    stale = browser.patch(
        f"{API}/notes/{note.id}", json={"content": "B", "expected_revision": 1}, headers=headers
    )

    assert first.status_code == 200 and first.json()["revision"] == 2
    assert stale.status_code == 409
    assert stale.json()["error"] == "conflict"
