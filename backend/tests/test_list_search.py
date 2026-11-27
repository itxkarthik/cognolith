"""List searches match the typed text literally and case-insensitively (issue #22)."""

import pytest
from sqlmodel import Session

from app import crud
from app.models.document import Document, DocumentChunks
from app.models.user import User, UserCreate
from app.schemas.note import NoteCreate
from app.services import document_service, note_service


@pytest.fixture
def user(session: Session) -> User:
    return crud.create_user(
        session=session,
        user_create=UserCreate(email="search@example.com", password="secure-password"),
    )


def _note_titles(session: Session, user: User, search: str) -> set[str]:
    notes, total = note_service.list_notes(session=session, current_user=user, search=search)
    assert total == len(notes)
    return {note.title for note in notes}


def _add_document(session: Session, user: User, title: str, chunk: str) -> None:
    document = Document(
        user_id=user.id,
        title=title,
        file_name=f"{title}.txt",
        file_path=f"/tmp/{title}.txt",
        file_size=len(chunk),
        file_type=".txt",
        mime_type="text/plain",
        status="completed",
        content=chunk,
    )
    session.add(document)
    session.flush()
    session.add(
        DocumentChunks(document_id=document.id, chunk_index=0, content=chunk, vector_id=title)
    )
    session.commit()


def _document_titles(session: Session, user: User, search: str) -> set[str]:
    documents, total = document_service.list_documents(
        session=session, current_user=user, search=search
    )
    assert total == len(documents)
    return {document.title for document in documents}


@pytest.mark.parametrize(
    ("search", "expected"),
    [
        ("50%", {"50% off"}),  # % is not a wildcard
        ("a_b", {"a_b"}),  # _ is not a wildcard
        ("x/y", {"x/y"}),  # the escape character itself
        ("OFF", {"50% off", "500 off"}),  # case-insensitive
    ],
)
def test_note_search_treats_wildcards_literally(
    session: Session, user: User, search: str, expected: set[str]
) -> None:
    for title in ["50% off", "500 off", "a_b", "axb", "x/y"]:
        note_service.create_note(
            session=session, current_user=user, payload=NoteCreate(title=title, content="body")
        )

    assert _note_titles(session, user, search) == expected


def test_note_search_matches_content(session: Session, user: User) -> None:
    note_service.create_note(
        session=session,
        current_user=user,
        payload=NoteCreate(title="Plain", content="Discount is 100% today"),
    )

    assert _note_titles(session, user, "100%") == {"Plain"}


def test_document_search_matches_title_and_chunk_text_literally(
    session: Session, user: User
) -> None:
    _add_document(session, user, "Pricing_2026", "Nothing to see here")
    _add_document(session, user, "Report", "Revenue grew 40% in Q3")
    _add_document(session, user, "Other", "Revenue grew 400 units")

    assert _document_titles(session, user, "pricing_2026") == {"Pricing_2026"}
    assert _document_titles(session, user, "40%") == {"Report"}
    assert _document_titles(session, user, "%") == {"Report"}
