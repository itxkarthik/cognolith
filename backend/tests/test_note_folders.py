"""Deleting, renaming and moving folders keeps notes and subfolders visible (issue #15)."""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, select

from app import crud
from app.core.config import settings
from app.main import app
from app.models.note import NoteFolders, Notes
from app.models.user import User, UserCreate
from app.schemas.note import FolderCreate, FolderUpdate
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
