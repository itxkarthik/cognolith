"""Deleting, renaming and moving folders keeps notes and subfolders visible (issue #15)."""

import threading
from collections.abc import Callable
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, select

from app import crud
from app.core.config import settings
from app.core.database import engine
from app.main import app
from app.models.note import NoteFolders, Notes
from app.models.user import User, UserCreate
from app.schemas.note import FolderCreate, FolderUpdate
from app.services import note_service
from app.services.note_service import create_folder, delete_folder, list_folders, update_folder

API = settings.API_V1_STR
EMAIL = "folders@example.com"
PASSWORD = "secure-password"


@pytest.fixture
def user(session: Session) -> User:
    return crud.create_user(session=session, user_create=UserCreate(email=EMAIL, password=PASSWORD))


def _folder(
    session: Session, user: User, name: str, parent: NoteFolders | None = None
) -> NoteFolders:
    return create_folder(
        session=session,
        current_user=user,
        payload=FolderCreate(name=name, parent_folder_id=parent.id if parent else None),
    )


def _note(session: Session, user: User, folder: NoteFolders | None, title: str) -> Notes:
    note = Notes(
        user_id=user.id, title=title, content="body", folder_id=folder.id if folder else None
    )
    session.add(note)
    session.commit()
    session.refresh(note)
    return note


def _reload[T: SQLModel](session: Session, model: type[T], row_id: int | None) -> T | None:
    session.expire_all()
    return session.get(model, row_id)


def _fresh[T: SQLModel](session: Session, model: type[T], row_id: int | None) -> T:
    row = _reload(session, model, row_id)
    assert row is not None
    return row


def test_deleting_a_folder_moves_its_contents_to_the_parent(session: Session, user: User) -> None:
    parent = _folder(session, user, "Projects")
    doomed = _folder(session, user, "Atlas", parent)
    child = _folder(session, user, "Drafts", doomed)
    note = _note(session, user, doomed, "Plan")
    assert doomed.id is not None

    delete_folder(session=session, current_user=user, folder_id=doomed.id)

    assert _reload(session, NoteFolders, doomed.id) is None
    assert _fresh(session, Notes, note.id).folder_id == parent.id
    assert _fresh(session, NoteFolders, child.id).parent_folder_id == parent.id
    assert {folder.name for folder in list_folders(session=session, current_user=user)} == {
        "Projects",
        "Drafts",
    }


def test_deleting_keeps_contents_already_loaded_in_the_session(
    session: Session, user: User
) -> None:
    # Loaded collections must not decide the outcome: `subfolders` cascades
    # delete-orphan and `notes` would be detached to the root on delete
    parent = _folder(session, user, "Projects")
    doomed = _folder(session, user, "Atlas", parent)
    child = _folder(session, user, "Drafts", doomed)
    note = _note(session, user, doomed, "Plan")
    assert doomed.id is not None
    assert [folder.id for folder in doomed.subfolders] == [child.id]
    assert [loaded.id for loaded in doomed.notes] == [note.id]

    delete_folder(session=session, current_user=user, folder_id=doomed.id)

    assert _fresh(session, NoteFolders, child.id).parent_folder_id == parent.id
    assert _fresh(session, Notes, note.id).folder_id == parent.id


def test_deleting_a_top_level_folder_moves_contents_to_the_root(
    session: Session, user: User
) -> None:
    doomed = _folder(session, user, "Inbox")
    note = _note(session, user, doomed, "Loose")
    child = _folder(session, user, "Later", doomed)
    assert doomed.id is not None

    delete_folder(session=session, current_user=user, folder_id=doomed.id)

    assert _fresh(session, Notes, note.id).folder_id is None
    assert _fresh(session, NoteFolders, child.id).parent_folder_id is None


def test_a_moved_subfolder_with_a_taken_name_is_renamed(session: Session, user: User) -> None:
    parent = _folder(session, user, "Work")
    _folder(session, user, "Archive", parent)
    _folder(session, user, "Archive (2)", parent)
    doomed = _folder(session, user, "Old", parent)
    moved = _folder(session, user, "Archive", doomed)
    assert doomed.id is not None

    delete_folder(session=session, current_user=user, folder_id=doomed.id)

    assert _fresh(session, NoteFolders, moved.id).name == "Archive (3)"


def test_deleting_frees_the_name_for_a_new_folder(session: Session, user: User) -> None:
    doomed = _folder(session, user, "Reused")
    assert doomed.id is not None

    delete_folder(session=session, current_user=user, folder_id=doomed.id)

    assert _folder(session, user, "Reused").name == "Reused"


def test_a_duplicate_folder_name_is_a_conflict_not_a_server_error(
    session: Session, user: User
) -> None:
    _folder(session, user, "Same")

    with pytest.raises(HTTPException) as raised:
        _folder(session, user, "Same")

    assert raised.value.status_code == 409


def test_a_folder_cannot_move_into_its_own_subfolder(session: Session, user: User) -> None:
    top = _folder(session, user, "Top")
    middle = _folder(session, user, "Middle", top)
    bottom = _folder(session, user, "Bottom", middle)
    assert top.id is not None

    for target in (top, bottom):
        with pytest.raises(HTTPException) as raised:
            update_folder(
                session=session,
                current_user=user,
                folder_id=top.id,
                payload=FolderUpdate(parent_folder_id=target.id),
            )
        assert raised.value.status_code == 409


def test_update_changes_only_the_fields_sent(session: Session, user: User) -> None:
    parent = _folder(session, user, "Parent")
    folder = _folder(session, user, "Child", parent)
    assert folder.id is not None

    renamed = update_folder(
        session=session, current_user=user, folder_id=folder.id, payload=FolderUpdate(name="Kid")
    )
    assert (renamed.name, renamed.parent_folder_id) == ("Kid", parent.id)

    moved = update_folder(
        session=session,
        current_user=user,
        folder_id=folder.id,
        payload=FolderUpdate.model_validate({"parent_folder_id": None}),
    )
    assert (moved.name, moved.parent_folder_id) == ("Kid", None)


def test_another_users_folder_is_not_found(session: Session, user: User) -> None:
    other = crud.create_user(
        session=session, user_create=UserCreate(email="other@example.com", password=PASSWORD)
    )
    theirs = _folder(session, other, "Private")
    assert theirs.id is not None

    with pytest.raises(HTTPException) as raised:
        delete_folder(session=session, current_user=user, folder_id=theirs.id)

    assert raised.value.status_code == 404
    assert session.exec(select(NoteFolders).where(NoteFolders.id == theirs.id)).first()


def test_folder_routes_rename_and_delete(session: Session, user: User) -> None:
    folder = _folder(session, user, "Via API")
    note = _note(session, user, folder, "Inside")
    browser = TestClient(app)
    assert (
        browser.post(
            f"{API}/login/access-token", data={"username": EMAIL, "password": PASSWORD}
        ).status_code
        == 200
    )
    headers = {settings.CSRF_HEADER_NAME: browser.cookies.get(settings.CSRF_COOKIE_NAME) or ""}

    renamed = browser.patch(
        f"{API}/notes/folders/{folder.id}", json={"name": "Renamed"}, headers=headers
    )
    deleted = browser.delete(f"{API}/notes/folders/{folder.id}", headers=headers)
    missing = browser.delete(f"{API}/notes/folders/{folder.id}", headers=headers)

    assert renamed.status_code == 200 and renamed.json()["name"] == "Renamed"
    assert deleted.status_code == 200
    assert missing.status_code == 404
    assert _fresh(session, Notes, note.id).folder_id is None


def _pause_for_the_other_request(monkeypatch: pytest.MonkeyPatch, name: str) -> threading.Barrier:
    """
    Make `note_service.<name>` wait (up to a second) for a second request to reach it
    too, so two requests interleave where an unserialized pair would.
    """
    barrier = threading.Barrier(2, timeout=1)
    original = getattr(note_service, name)

    def paused(*args: object, **kwargs: object) -> object:
        result = original(*args, **kwargs)
        try:
            barrier.wait()
        except threading.BrokenBarrierError:
            pass  # the other request is held back by the lock
        return result

    monkeypatch.setattr(note_service, name, paused)
    return barrier


def _as_user(user: User, work: Callable[[Session, User], object]) -> Callable[[], None]:
    def run() -> None:
        with Session(engine) as own_session:
            own_user = own_session.get(User, user.id)
            assert own_user is not None
            work(own_session, own_user)

    return run


def _run_together(*targets: Callable[[], None]) -> list[str]:
    outcomes: list[str] = []

    def record(target: Callable[[], None]) -> None:
        try:
            target()
            outcomes.append("ok")
        except HTTPException as exc:
            outcomes.append(str(exc.status_code))

    threads = [threading.Thread(target=record, args=(target,)) for target in targets]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return sorted(outcomes)


def test_crossed_moves_cannot_make_a_loop(
    session: Session, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = _folder(session, user, "A")
    b = _folder(session, user, "B")
    assert a.id is not None and b.id is not None
    a_id, b_id = a.id, b.id
    _pause_for_the_other_request(monkeypatch, "_folder_subtree_ids")

    def move(folder_id: int, parent_id: int) -> Callable[[], None]:
        return _as_user(
            user,
            lambda own_session, own_user: update_folder(
                session=own_session,
                current_user=own_user,
                folder_id=folder_id,
                payload=FolderUpdate(parent_folder_id=parent_id),
            ),
        )

    assert _run_together(move(a_id, b_id), move(b_id, a_id)) == ["409", "ok"]
    parents = {
        _fresh(session, NoteFolders, a_id).parent_folder_id,
        _fresh(session, NoteFolders, b_id).parent_folder_id,
    }
    assert None in parents  # one of them is still reachable from the root


def test_a_folder_created_during_a_delete_is_not_lost(
    session: Session, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent = _folder(session, user, "Projects")
    doomed = _folder(session, user, "Atlas", parent)
    assert doomed.id is not None and parent.id is not None
    doomed_id = doomed.id
    created = threading.Event()
    original = note_service._folder_names

    def names_then_wait(*args: Any, **kwargs: Any) -> set[str]:
        # The delete has read the folder's children; a new child lands now
        result = original(*args, **kwargs)
        created.wait(timeout=1)
        return result

    monkeypatch.setattr(note_service, "_folder_names", names_then_wait)

    def create_child(own_session: Session, own_user: User) -> object:
        try:
            return _folder(own_session, own_user, "Late", own_session.get(NoteFolders, doomed_id))
        finally:
            created.set()

    outcomes = _run_together(
        _as_user(
            user,
            lambda own_session, own_user: delete_folder(
                session=own_session, current_user=own_user, folder_id=doomed_id
            ),
        ),
        _as_user(user, create_child),
    )

    late = session.exec(select(NoteFolders).where(NoteFolders.name == "Late")).all()
    if outcomes == ["ok", "ok"]:
        assert [folder.parent_folder_id for folder in late] == [parent.id]
    else:
        assert outcomes == ["404", "ok"] and late == []


def test_a_renamed_subfolder_still_fits_the_name_limit(session: Session, user: User) -> None:
    long_name = "x" * 255
    parent = _folder(session, user, "Projects")
    _folder(session, user, long_name, parent)
    doomed = _folder(session, user, "Atlas", parent)
    moved = _folder(session, user, long_name, doomed)
    assert doomed.id is not None

    delete_folder(session=session, current_user=user, folder_id=doomed.id)

    renamed = _fresh(session, NoteFolders, moved.id)
    assert renamed.parent_folder_id == parent.id
    assert renamed.name == "x" * 251 + " (2)"
