from datetime import UTC, datetime

from sqlmodel import Session, col, func, select

from app import crud
from app.models.note import Notes
from app.models.user import User, UserCreate
from app.schemas.note import NoteCreate, NoteUpdate
from app.services import note_service


def _user(session: Session) -> User:
    return crud.create_user(
        session=session,
        user_create=UserCreate(email="versions@example.com", password="secure-password"),
    )


def _note_id(note: Notes) -> int:
    assert note.id is not None
    return note.id


def _snapshot_count(session: Session) -> int:
    return session.exec(
        select(func.count()).select_from(Notes).where(col(Notes.is_deleted).is_(True))
    ).one()


def _age_latest_snapshot(session: Session, note: Notes) -> None:
    assert note.previous_version_id is not None
    snapshot = session.get(Notes, note.previous_version_id)
    assert snapshot is not None
    snapshot.created_at = datetime.now(UTC) - note_service.NOTE_VERSION_INTERVAL * 2
    session.add(snapshot)
    session.commit()


def test_rapid_autosaves_create_one_snapshot(session: Session) -> None:
    user = _user(session)
    note = note_service.create_note(
        session=session, current_user=user, payload=NoteCreate(title="Draft", content="one")
    )

    for content in ["one two", "one two three", "one two three four"]:
        note = note_service.update_note(
            session=session,
            current_user=user,
            note_id=_note_id(note),
            payload=NoteUpdate(content=content),
        )

    assert _snapshot_count(session) == 1
    assert note.version == 2


def test_snapshot_is_taken_again_after_the_interval(session: Session) -> None:
    user = _user(session)
    note = note_service.create_note(
        session=session, current_user=user, payload=NoteCreate(title="Draft", content="one")
    )
    note = note_service.update_note(
        session=session, current_user=user, note_id=_note_id(note), payload=NoteUpdate(content="two")
    )
    _age_latest_snapshot(session, note)

    note = note_service.update_note(
        session=session, current_user=user, note_id=_note_id(note), payload=NoteUpdate(content="three")
    )

    assert _snapshot_count(session) == 2
    assert note.version == 3


def test_metadata_only_updates_do_not_snapshot(session: Session) -> None:
    user = _user(session)
    note = note_service.create_note(
        session=session, current_user=user, payload=NoteCreate(title="Draft", content="one")
    )

    note_service.update_note(
        session=session, current_user=user, note_id=_note_id(note), payload=NoteUpdate(is_favorite=True)
    )

    assert _snapshot_count(session) == 0


def test_version_history_is_pruned_to_the_retention_limit(session: Session, monkeypatch) -> None:
    monkeypatch.setattr(note_service, "NOTE_VERSION_RETENTION", 2)
    user = _user(session)
    note = note_service.create_note(
        session=session, current_user=user, payload=NoteCreate(title="Draft", content="v0")
    )

    for index in range(1, 5):
        note = note_service.update_note(
            session=session,
            current_user=user,
            note_id=_note_id(note),
            payload=NoteUpdate(content=f"v{index}"),
        )
        _age_latest_snapshot(session, note)

    assert _snapshot_count(session) == 2
