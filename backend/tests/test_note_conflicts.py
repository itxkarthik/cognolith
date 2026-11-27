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
from app.models.note import Notes, NoteTags
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


def test_an_older_save_cannot_overwrite_newer_tags(
    session: Session, user: User, note: Notes, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert user.id is not None
    old_tag = NoteTags(user_id=user.id, name="old")
    new_tag = NoteTags(user_id=user.id, name="new")
    session.add_all([old_tag, new_tag])
    session.commit()
    assert note.id is not None and old_tag.id is not None and new_tag.id is not None
    note_id, old_id, new_id = note.id, old_tag.id, new_tag.id
    first_committed = threading.Event()
    second_done = threading.Event()
    errors: list[BaseException] = []

    def first_save() -> None:
        with Session(engine) as own_session:
            commit = own_session.commit

            def commit_then_pause() -> None:
                commit()
                if not first_committed.is_set():
                    # A newer save lands right after this one's first commit
                    first_committed.set()
                    second_done.wait(timeout=5)

            own_session.commit = commit_then_pause  # type: ignore[method-assign]
            own_user = own_session.get(User, user.id)
            assert own_user is not None
            try:
                update_note(
                    session=own_session,
                    current_user=own_user,
                    note_id=note_id,
                    payload=NoteUpdate(content="first", tag_ids=[old_id], expected_revision=1),
                )
            except BaseException as exc:  # surfaced below
                errors.append(exc)

    def second_save() -> None:
        first_committed.wait(timeout=5)
        try:
            with Session(engine) as own_session:
                own_user = own_session.get(User, user.id)
                assert own_user is not None
                update_note(
                    session=own_session,
                    current_user=own_user,
                    note_id=note_id,
                    payload=NoteUpdate(content="second", tag_ids=[new_id], expected_revision=2),
                )
        except BaseException as exc:
            errors.append(exc)
        finally:
            second_done.set()

    threads = [threading.Thread(target=first_save), threading.Thread(target=second_save)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    session.expire_all()
    saved = session.get(Notes, note_id)
    assert saved is not None
    assert saved.revision == 3
    assert [tag.id for tag in saved.tags] == [new_id]
