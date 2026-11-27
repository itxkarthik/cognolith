"""Timestamps are stored as UTC, never as the server's local time (issue #20)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import Session

from app import crud
from app.models.chat import ChatSession
from app.models.document import Document
from app.models.note import Notes
from app.models.user import ActivityLogs, UserCreate
from app.schemas.note import NoteCreate, NoteUpdate
from app.services import note_service


def _as_utc(value: datetime) -> datetime:
    # timestamp columns come back naive; they hold UTC wall-clock time
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def test_note_edit_time_is_stored_in_utc(session: Session) -> None:
    user = crud.create_user(
        session=session,
        user_create=UserCreate(email="clock@example.com", password="secure-password"),
    )
    note = note_service.create_note(
        session=session, current_user=user, payload=NoteCreate(title="Draft", content="one")
    )
    assert note.id is not None

    note_service.update_note(
        session=session,
        current_user=user,
        note_id=note.id,
        payload=NoteUpdate(content="one two"),
    )
    session.expire_all()
    stored = session.get(Notes, note.id)

    assert stored is not None
    # A local-time write would be off by the server's UTC offset (hours, not seconds)
    assert abs(_as_utc(stored.last_edited_at) - datetime.now(UTC)) < timedelta(minutes=1)


@pytest.mark.parametrize(
    ("model", "field"),
    [
        (ChatSession, "last_message_at"),
        (Notes, "last_edited_at"),
        (Notes, "last_accessed_at"),
        (Document, "last_accessed_at"),
        (ActivityLogs, "created_at"),
    ],
)
def test_timestamp_defaults_are_utc(model: type, field: str) -> None:
    default = model.model_fields[field].default_factory()

    assert default.utcoffset() == timedelta(0)
