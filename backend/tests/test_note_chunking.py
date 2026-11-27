"""Notes are embedded per chunk, so their whole text is searchable (issue #17)."""

from collections.abc import Sequence

import pytest
from sqlalchemy import text
from sqlmodel import Session

from app.ai import rag
from app.ai.chunking import chunk_note
from app.ai.vectorstore import PgVectorStore
from app.core.config import settings
from app.models.note import Notes
from app.models.user import User, UserSettings

MODEL = "test-embedder"


def _direction(index: int) -> list[float]:
    vector = [0.0] * settings.EMBEDDING_DIMENSIONS
    vector[index] = 1.0
    return vector


NEEDLE = _direction(1)


async def _fake_embeddings(*, texts: Sequence[str], **_: object) -> tuple[list[list[float]], str]:
    # Passages mentioning the needle point one way, everything else another
    return [NEEDLE if "needle" in item else _direction(0) for item in texts], MODEL


@pytest.fixture
def user(session: Session) -> User:
    user = User(email="note-chunks@example.com", hashed_password="unused", is_verified=True)
    session.add(user)
    session.commit()
    session.refresh(user)
    assert user.id is not None
    session.add(UserSettings(user_id=user.id, chunk_size=200, chunk_overlap=20))
    session.commit()
    return user


@pytest.fixture
def store(session: Session, monkeypatch: pytest.MonkeyPatch) -> PgVectorStore:
    monkeypatch.setattr(rag, "generate_embeddings", _fake_embeddings)
    vector_store = PgVectorStore(session=session)
    vector_store.ensure_schema(embedding_dimensions=settings.EMBEDDING_DIMENSIONS)
    return vector_store


def _index(session: Session, store: PgVectorStore, user: User) -> None:
    assert user.id is not None
    rag.ensure_workspace_embeddings(
        session=session, vector_store=store, user_id=user.id, embedding_model=MODEL
    )


def _search(store: PgVectorStore, user: User, top_k: int = 5):
    assert user.id is not None
    return store.note_similarity_search(
        user_id=user.id,
        model=MODEL,
        query_embedding=NEEDLE,
        top_k=top_k,
        similarity_threshold=0.5,
    )


def _stored_chunks(session: Session, note: Notes) -> list[int]:
    rows = session.connection().execute(
        text("SELECT chunk_index FROM note_embeddings WHERE note_id = :id ORDER BY chunk_index"),
        {"id": note.id},
    )
    return [row.chunk_index for row in rows]


def test_chunk_note_splits_and_titles_each_passage() -> None:
    note = Notes(id=1, user_id=1, title="Atlas", content="word " * 100)

    chunks = chunk_note(note, chunk_size=200, overlap=20)

    assert len(chunks) > 1
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))
    assert all(chunk.embedding_text.startswith("Atlas\n\n") for chunk in chunks)
    assert len({chunk.content_hash for chunk in chunks}) == 1


def test_chunk_note_hash_changes_with_chunk_settings() -> None:
    note = Notes(id=1, user_id=1, title="Atlas", content="word " * 100)

    first = chunk_note(note, chunk_size=200, overlap=20)[0].content_hash
    second = chunk_note(note, chunk_size=300, overlap=20)[0].content_hash

    assert first != second


def test_text_past_the_old_12k_limit_is_found_and_cited(
    session: Session, store: PgVectorStore, user: User
) -> None:
    note = Notes(
        user_id=user.id, title="Long", content="filler text. " * 1200 + "the needle is here."
    )
    session.add(note)
    session.commit()
    assert len(note.content) > 12_000

    _index(session, store, user)
    hits = _search(store, user)

    assert [hit.note_id for hit in hits] == [note.id]
    assert "needle" in hits[0].content
    assert hits[0].chunk_index > 0
    assert len(hits[0].content) <= 200


def test_a_long_note_takes_one_result_slot(
    session: Session, store: PgVectorStore, user: User
) -> None:
    many = Notes(user_id=user.id, title="Many", content="needle again. " * 200)
    other = Notes(user_id=user.id, title="Other", content="a single needle.")
    session.add_all([many, other])
    session.commit()

    _index(session, store, user)
    hits = _search(store, user, top_k=2)

    assert {hit.note_id for hit in hits} == {many.id, other.id}


def test_editing_a_note_replaces_all_its_chunks(
    session: Session, store: PgVectorStore, user: User
) -> None:
    note = Notes(user_id=user.id, title="Shrinks", content="needle words. " * 100)
    session.add(note)
    session.commit()
    _index(session, store, user)
    assert len(_stored_chunks(session, note)) > 1

    note.content = "short now"
    session.add(note)
    session.commit()
    _index(session, store, user)

    assert _stored_chunks(session, note) == [0]
    assert _search(store, user) == []


def test_emptying_a_note_removes_its_chunks(
    session: Session, store: PgVectorStore, user: User
) -> None:
    note = Notes(user_id=user.id, title="", content="the needle")
    session.add(note)
    session.commit()
    _index(session, store, user)
    assert _stored_chunks(session, note) == [0]

    note.content = "   "
    session.add(note)
    session.commit()
    _index(session, store, user)

    assert _stored_chunks(session, note) == []


def test_batches_never_split_a_note() -> None:
    note_id_chunks = [
        chunk_note(
            Notes(id=index, user_id=1, title="", content="x " * size), chunk_size=200, overlap=0
        )
        for index, size in enumerate((150, 900, 150), start=1)
    ]

    batches = list(rag._whole_note_batches(note_id_chunks, max_chunks=4))

    for batch in batches:
        for note_id in {chunk.note_id for chunk in batch}:
            assert sum(1 for other in batches if any(c.note_id == note_id for c in other)) == 1
    assert sum(len(batch) for batch in batches) == sum(len(c) for c in note_id_chunks)
