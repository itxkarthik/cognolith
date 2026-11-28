"""Content is embedded in the background, never on the read path (issue #24)."""

import asyncio
import threading
import time
from collections.abc import Sequence

import pytest
from sqlalchemy import func, text
from sqlmodel import Session, select

from app.ai import rag
from app.ai.embeddings import resolve_embedding_model
from app.ai.vectorstore import PgVectorStore
from app.core.config import settings
from app.core.database import engine
from app.models.document import Document, DocumentChunks
from app.models.note import Notes
from app.models.user import User
from app.services import workspace_indexer as indexer_module
from app.services.workspace_indexer import (
    INDEX_LOCK_CLASS,
    WorkspaceIndexer,
    index_user_workspace,
    workspace_indexer,
)

VECTOR = [1.0] + [0.0] * (settings.EMBEDDING_DIMENSIONS - 1)


async def _fake_embeddings(*, texts: Sequence[str], **_: object) -> tuple[list[list[float]], str]:
    return [VECTOR for _ in texts], "test-embedder"


async def _fake_embedding(*, text: str, **_: object) -> tuple[list[float], str]:
    del text
    return VECTOR, "test-embedder"


@pytest.fixture
def user(session: Session) -> User:
    user = User(email="indexer@example.com", hashed_password="unused", is_verified=True)
    session.add(user)
    session.commit()
    session.refresh(user)
    assert user.id is not None
    return user


def _note_vectors(session: Session, note_id: int) -> int:
    return (
        session.connection()
        .execute(text("SELECT count(*) FROM note_embeddings WHERE note_id = :id"), {"id": note_id})
        .scalar_one()
    )


# --- the read path -----------------------------------------------------------------


def test_retrieval_never_embeds_the_workspace(
    session: Session, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    session.add(Notes(user_id=user.id, title="Unindexed", content="Fresh text"))
    session.commit()
    embedded: list[int] = []

    async def counting_embeddings(*, texts: Sequence[str], **kwargs: object):
        embedded.append(len(texts))
        return await _fake_embeddings(texts=texts, **kwargs)

    monkeypatch.setattr(rag, "generate_embeddings", counting_embeddings)
    monkeypatch.setattr(rag, "generate_embedding", _fake_embedding)
    assert user.id is not None

    rag.prepare_rag_pipeline(
        session=session, user_id=user.id, query="fresh text", conversation_history=[]
    )

    assert embedded == []  # only the question was embedded


# --- marking owners on commit ------------------------------------------------------


def test_saving_a_note_marks_its_owner_for_indexing(session: Session, user: User) -> None:
    assert user.id is not None
    with workspace_indexer._lock:  # pyright: ignore[reportPrivateUsage]
        workspace_indexer._due.clear()  # pyright: ignore[reportPrivateUsage]

    note = Notes(user_id=user.id, title="Draft", content="v1")
    session.add(note)
    session.flush()
    assert user.id not in workspace_indexer.pending()  # not before the commit
    session.commit()
    assert user.id in workspace_indexer.pending()


# --- indexing ----------------------------------------------------------------------


def test_indexing_embeds_new_notes_and_missing_chunks(
    session: Session, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rag, "generate_embeddings", _fake_embeddings)
    assert user.id is not None
    note = Notes(user_id=user.id, title="Atlas", content="Launch window notes")
    document = Document(
        user_id=user.id,
        title="Doc",
        file_name="d.txt",
        file_path="/tmp/d.txt",
        file_size=1,
        file_type=".txt",
        mime_type="text/plain",
        status="completed",
    )
    session.add_all([note, document])
    session.flush()
    session.add(
        DocumentChunks(document_id=document.id, chunk_index=0, content="chunk", vector_id="v")
    )
    session.commit()
    assert note.id is not None
    store = PgVectorStore(session=session)
    model = resolve_embedding_model(session=session, user_id=user.id)
    assert len(store.unindexed_document_chunks(user_id=user.id, model=model)) == 1

    assert index_user_workspace(user.id) is True

    session.expire_all()
    assert _note_vectors(session, note.id) > 0
    assert store.unindexed_document_chunks(user_id=user.id, model=model) == []


def test_a_user_another_process_is_indexing_is_left_to_it(
    session: Session, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rag, "generate_embeddings", _fake_embeddings)
    assert user.id is not None
    note = Notes(user_id=user.id, title="Atlas", content="Launch window notes")
    session.add(note)
    session.commit()
    assert note.id is not None

    with Session(engine) as other_process:
        assert other_process.exec(
            select(func.pg_try_advisory_xact_lock(INDEX_LOCK_CLASS, user.id))
        ).one()
        assert index_user_workspace(user.id) is False
        other_process.rollback()

    assert _note_vectors(session, note.id) == 0
    assert index_user_workspace(user.id) is True


# --- scheduling --------------------------------------------------------------------


def test_a_burst_of_changes_is_indexed_once() -> None:
    runs: list[int] = []

    def index(user_id: int) -> bool:
        runs.append(user_id)
        return True

    indexer = WorkspaceIndexer(index_user=index, debounce_seconds=0.05)
    for _ in range(5):
        indexer.mark_dirty(7)

    async def scenario() -> None:
        await indexer.run_due()
        assert runs == []  # still within the debounce
        await asyncio.sleep(0.06)
        await indexer.run_due()

    asyncio.run(scenario())
    assert runs == [7]


def test_a_failed_or_locked_run_is_retried() -> None:
    outcomes = iter([RuntimeError("model down"), False, True])
    runs: list[int] = []

    def index(user_id: int) -> bool:
        runs.append(user_id)
        outcome = next(outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    indexer = WorkspaceIndexer(index_user=index, debounce_seconds=0, retry_seconds=0)
    indexer.mark_dirty(3)

    async def scenario() -> None:
        for _ in range(3):
            await indexer.run_due()
            await asyncio.sleep(0.001)

    asyncio.run(scenario())
    assert runs == [3, 3, 3]
    assert indexer.pending() == set()


def test_startup_catches_up_every_user(user: User, monkeypatch: pytest.MonkeyPatch) -> None:
    indexed: list[int] = []

    def index(user_id: int) -> bool:
        indexed.append(user_id)
        return True

    monkeypatch.setattr(indexer_module, "DEBOUNCE_SECONDS", 0)
    indexer = WorkspaceIndexer(index_user=index, debounce_seconds=0, poll_seconds=0.01)

    async def scenario() -> None:
        await indexer.start()
        await asyncio.sleep(0.1)
        await indexer.stop()

    asyncio.run(scenario())
    assert indexed == [user.id]


def test_a_long_index_run_does_not_hold_up_other_users() -> None:
    slow_started = threading.Event()
    release_slow = threading.Event()
    indexed: list[int] = []

    def index(user_id: int) -> bool:
        if user_id == 1:
            slow_started.set()
            release_slow.wait(5)  # a large import
        indexed.append(user_id)
        return True

    indexer = WorkspaceIndexer(index_user=index, debounce_seconds=0, poll_seconds=0.01)

    async def scenario() -> list[int]:
        indexer.mark_dirty(1)
        await indexer.start_loop()
        await asyncio.to_thread(slow_started.wait, 5)
        indexer.mark_dirty(2)
        for _ in range(100):
            if 2 in indexed:
                break
            await asyncio.sleep(0.01)
        done_while_slow = list(indexed)
        release_slow.set()
        await indexer.stop()
        return done_while_slow

    assert asyncio.run(scenario()) == [2]


def test_one_user_is_never_indexed_twice_at_once() -> None:
    running: set[int] = set()
    overlapped = False
    lock = threading.Lock()

    def index(user_id: int) -> bool:
        nonlocal overlapped
        with lock:
            overlapped = overlapped or user_id in running
            running.add(user_id)
        time.sleep(0.05)
        with lock:
            running.discard(user_id)
        return True

    indexer = WorkspaceIndexer(index_user=index, debounce_seconds=0, poll_seconds=0.005)

    async def scenario() -> None:
        await indexer.start_loop()
        for _ in range(10):
            indexer.mark_dirty(4)  # saved again while being indexed
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.1)
        await indexer.stop()

    asyncio.run(scenario())
    assert not overlapped
