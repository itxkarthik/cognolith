"""Similarity search only compares vectors from the query's model (issue #16)."""

from datetime import UTC, datetime

import pytest
from sqlmodel import Session

from app.ai.vectorstore import PgVectorStore
from app.core.config import settings
from app.models.chat import ChatMessages, ChatRole, ChatSession
from app.models.document import Document, DocumentChunks
from app.models.note import Notes
from app.models.user import User

OLD_MODEL = "old-embedder"
NEW_MODEL = "new-embedder"


def _vector() -> list[float]:
    # Same direction for every row: only the model filter can tell them apart
    return [1.0] + [0.0] * (settings.EMBEDDING_DIMENSIONS - 1)


@pytest.fixture
def store(session: Session) -> PgVectorStore:
    vector_store = PgVectorStore(session=session)
    vector_store.ensure_schema(embedding_dimensions=settings.EMBEDDING_DIMENSIONS)
    return vector_store


@pytest.fixture
def user(session: Session) -> User:
    user = User(email="model-filter@example.com", hashed_password="unused", is_verified=True)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _user_id(user: User) -> int:
    assert user.id is not None
    return user.id


def test_document_search_ignores_chunks_from_another_model(
    session: Session, store: PgVectorStore, user: User
) -> None:
    document = Document(
        user_id=user.id,
        title="Doc",
        file_name="doc.md",
        file_path="/tmp/doc.md",
        file_size=10,
        file_type="markdown",
        mime_type="text/markdown",
        status="completed",
    )
    session.add(document)
    session.commit()
    chunks = [
        DocumentChunks(
            document_id=document.id,
            chunk_index=index,
            content=f"chunk {index}",
            vector_id=f"chunk-{index}",
        )
        for index in range(2)
    ]
    session.add_all(chunks)
    session.commit()
    for chunk, model in zip(chunks, (OLD_MODEL, NEW_MODEL), strict=True):
        session.refresh(chunk)
        store.store_document_chunk_embeddings(
            chunks=[chunk], embeddings=[_vector()], user_id=_user_id(user), model=model
        )

    hits = store.similarity_search(
        user_id=_user_id(user), model=NEW_MODEL, query_embedding=_vector(), top_k=10
    )

    assert [hit.chunk_id for hit in hits] == [chunks[1].id]


def test_note_search_ignores_notes_from_another_model(
    session: Session, store: PgVectorStore, user: User
) -> None:
    notes = [Notes(user_id=user.id, title=f"Note {index}", content="body") for index in range(2)]
    session.add_all(notes)
    session.commit()
    for note, model in zip(notes, (OLD_MODEL, NEW_MODEL), strict=True):
        session.refresh(note)
        assert note.id is not None
        store.store_note_embeddings(
            notes=[(note.id, "hash")], embeddings=[_vector()], user_id=_user_id(user), model=model
        )

    hits = store.note_similarity_search(
        user_id=_user_id(user), model=NEW_MODEL, query_embedding=_vector(), top_k=10
    )

    assert [hit.note_id for hit in hits] == [notes[1].id]


def test_chat_search_ignores_messages_from_another_model(
    session: Session, store: PgVectorStore, user: User
) -> None:
    chat = ChatSession(user_id=user.id, title="Chat", last_message_at=datetime.now(UTC))
    session.add(chat)
    session.commit()
    messages = [
        ChatMessages(session_id=chat.id, role=ChatRole.user, content=f"message {index}")
        for index in range(2)
    ]
    session.add_all(messages)
    session.commit()
    for message, model in zip(messages, (OLD_MODEL, NEW_MODEL), strict=True):
        session.refresh(message)
        assert message.id is not None and chat.id is not None
        store.store_chat_message_embeddings(
            messages=[(message.id, chat.id, "hash")],
            embeddings=[_vector()],
            user_id=_user_id(user),
            model=model,
        )

    hits = store.chat_similarity_search(
        user_id=_user_id(user), model=NEW_MODEL, query_embedding=_vector(), top_k=10
    )

    assert [hit.message_id for hit in hits] == [messages[1].id]
