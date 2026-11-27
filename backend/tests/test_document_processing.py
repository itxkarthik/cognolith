"""Background document processing inside the API process."""

import asyncio
import threading
import time
from io import BytesIO
from typing import Any

import pytest
from fastapi import UploadFile
from sqlmodel import Session

from app import crud
from app.ai import rag
from app.ai.vectorstore import PgVectorStore
from app.core.config import settings
from app.models.document import Document, DocumentEmbeddingStatus
from app.models.user import User, UserCreate
from app.services import document_service
from app.services.document_processing import (
    ATTEMPTS_EXHAUSTED_ERROR,
    MAX_PROCESSING_ATTEMPTS,
    DocumentProcessor,
    ProcessingStoppedError,
    document_processor,
)

# Scheduling (no database)


def test_processing_is_limited_to_the_configured_concurrency() -> None:
    running = 0
    peak = 0
    lock = threading.Lock()

    def process(**_: Any) -> None:
        nonlocal running, peak
        with lock:
            running += 1
            peak = max(peak, running)
        time.sleep(0.05)
        with lock:
            running -= 1

    async def scenario() -> None:
        processor = DocumentProcessor(concurrency=2, process=process)
        for document_id in range(1, 6):
            processor.schedule(user_id=1, document_id=document_id)
        await processor.wait_idle()

    asyncio.run(scenario())

    assert peak == 2


def test_a_document_already_processing_is_not_scheduled_twice() -> None:
    calls: list[int] = []

    def process(*, document_id: int, **_: Any) -> None:
        calls.append(document_id)
        time.sleep(0.01)

    async def scenario() -> bool:
        processor = DocumentProcessor(process=process)
        assert processor.schedule(user_id=1, document_id=7) is True
        second = processor.schedule(user_id=1, document_id=7)
        await processor.wait_idle()
        return second

    assert asyncio.run(scenario()) is False
    assert calls == [7]


def test_a_failing_document_does_not_stop_the_others() -> None:
    done: list[int] = []

    def process(*, document_id: int, **_: Any) -> None:
        if document_id == 1:
            raise RuntimeError("corrupt file")
        done.append(document_id)

    async def scenario() -> None:
        processor = DocumentProcessor(process=process)
        for document_id in (1, 2):
            processor.schedule(user_id=1, document_id=document_id)
        await processor.wait_idle()

    asyncio.run(scenario())

    assert done == [2]


def test_shutdown_stops_in_flight_processing_and_waits_for_it() -> None:
    events: list[str] = []

    def process(*, stop: threading.Event, **_: Any) -> None:
        deadline = time.monotonic() + 10
        while not stop.is_set() and time.monotonic() < deadline:
            time.sleep(0.01)
        events.append("stopped" if stop.is_set() else "ran to the end")
        raise ProcessingStoppedError

    async def scenario() -> None:
        processor = DocumentProcessor(process=process)
        processor.schedule(user_id=1, document_id=1)
        await asyncio.sleep(0.05)
        await processor.shutdown()
        # Returned only once the run had stopped
        assert events == ["stopped"]

    asyncio.run(scenario())


def test_processing_runs_off_the_event_loop() -> None:
    gaps: list[float] = []

    def process(**_: Any) -> None:
        time.sleep(0.3)  # file parsing, database writes, model calls

    async def scenario() -> None:
        processor = DocumentProcessor(process=process)
        processor.schedule(user_id=1, document_id=1)
        last = time.perf_counter()
        for _ in range(20):
            await asyncio.sleep(0.01)
            now = time.perf_counter()
            gaps.append(now - last)
            last = now
        await processor.wait_idle()

    asyncio.run(scenario())

    assert max(gaps) < 0.1


# With the database


def _user(session: Session) -> User:
    return crud.create_user(
        session=session,
        user_create=UserCreate(email="processing@example.com", password="secure-password"),
    )


def _document(session: Session, user: User, path: str, status: str, **fields: Any) -> Document:
    document = Document(
        user_id=user.id,
        title="Doc",
        file_name=path.rsplit("/", 1)[-1],
        file_path=path,
        file_size=1,
        file_type="." + path.rsplit(".", 1)[-1],
        mime_type="text/plain",
        status=status,
        **fields,
    )
    session.add(document)
    session.commit()
    session.refresh(document)
    return document


@pytest.mark.asyncio
async def test_upload_returns_before_processing_then_completes_in_the_background(
    session: Session, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "UPLOAD_DIR", tmp_path)
    user = _user(session)

    document = await document_service.upload_and_process_document(
        current_user=user,
        file=UploadFile(
            filename="atlas.txt", file=BytesIO(b"The Atlas launch window is Friday morning.")
        ),
    )
    assert document.status == "processing"
    assert document.content is None

    await document_processor.wait_idle()

    session.expire_all()
    processed = session.get(Document, document.id)
    assert processed is not None
    assert processed.status == "completed"
    assert processed.content is not None and "Atlas launch window" in processed.content
    assert processed.chunk_count == 1


@pytest.mark.asyncio
async def test_a_failed_document_keeps_the_extraction_reason(session: Session, tmp_path) -> None:
    user = _user(session)
    corrupt = tmp_path / "broken.pdf"
    corrupt.write_bytes(b"this is not a pdf")
    document = _document(session, user, corrupt.as_posix(), "processing")
    assert document.id is not None and user.id is not None

    processor = DocumentProcessor()
    processor.schedule(user_id=user.id, document_id=document.id)
    await processor.wait_idle()

    session.expire_all()
    failed = session.get(Document, document.id)
    assert failed is not None
    assert failed.status == "failed"
    assert failed.processing_error == "Failed to read PDF file"


@pytest.mark.asyncio
async def test_startup_resumes_only_interrupted_documents(session: Session, tmp_path) -> None:
    user = _user(session)
    interrupted = _document(session, user, (tmp_path / "a.txt").as_posix(), "processing")
    _document(session, user, (tmp_path / "b.txt").as_posix(), "completed")
    _document(session, user, (tmp_path / "c.txt").as_posix(), "processing", is_deleted=True)
    resumed: list[int] = []

    def process(*, document_id: int, **_: Any) -> None:
        resumed.append(document_id)

    processor = DocumentProcessor(process=process)
    assert processor.resume_interrupted() == 1
    await processor.wait_idle()

    assert resumed == [interrupted.id]


# Embedding status and processing attempts (issue #21)


def _fake_embeddings(*, fail: bool = False):
    async def generate(*, texts: list[str], **_: Any) -> tuple[list[list[float]], str]:
        if fail:
            raise RuntimeError("embedding service down")
        vector = [1.0] + [0.0] * (settings.EMBEDDING_DIMENSIONS - 1)
        return [vector for _ in texts], "test-embedder"

    return generate


def _process(session: Session, user: User, document: Document) -> Document:
    assert user.id is not None and document.id is not None
    try:
        document_service.process_existing_document(
            session=session, user_id=user.id, document_id=document.id
        )
    except Exception:
        pass
    session.expire_all()
    processed = session.get(Document, document.id)
    assert processed is not None
    return processed


def _text_document(
    session: Session, user: User, tmp_path, content: str = "Atlas notes"
) -> Document:
    path = tmp_path / "atlas.txt"
    path.write_text(content)
    return _document(session, user, path.as_posix(), "processing")


def test_a_document_whose_embedding_fails_is_flagged(
    session: Session, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(document_service, "generate_embeddings", _fake_embeddings(fail=True))
    monkeypatch.setattr(document_service, "generate_document_summary", _no_summary)
    user = _user(session)

    processed = _process(session, user, _text_document(session, user, tmp_path))

    assert processed.status == "completed"
    assert processed.embedding_status == DocumentEmbeddingStatus.failed


def test_an_embedded_document_is_marked_indexed(session: Session, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(document_service, "generate_embeddings", _fake_embeddings())
    monkeypatch.setattr(document_service, "generate_document_summary", _no_summary)
    user = _user(session)

    processed = _process(session, user, _text_document(session, user, tmp_path))

    assert processed.embedding_status == DocumentEmbeddingStatus.indexed
    assert processed.processing_attempts == 1


def test_the_indexer_reindexes_a_failed_document(
    session: Session, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(document_service, "generate_embeddings", _fake_embeddings(fail=True))
    monkeypatch.setattr(document_service, "generate_document_summary", _no_summary)
    monkeypatch.setattr(rag, "generate_embeddings", _fake_embeddings())
    user = _user(session)
    document = _process(session, user, _text_document(session, user, tmp_path))
    assert document.embedding_status == DocumentEmbeddingStatus.failed
    assert user.id is not None

    vector_store = PgVectorStore(session=session)
    vector_store.ensure_schema(embedding_dimensions=settings.EMBEDDING_DIMENSIONS)
    rag.ensure_workspace_embeddings(
        session=session, vector_store=vector_store, user_id=user.id, embedding_model="test-embedder"
    )
    session.commit()

    session.expire_all()
    reindexed = session.get(Document, document.id)
    assert reindexed is not None
    assert reindexed.embedding_status == DocumentEmbeddingStatus.indexed


def test_extraction_that_hangs_times_out(session: Session, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "DOCUMENT_EXTRACTION_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(document_service, "extract_text_from_file", _slow_extract)
    user = _user(session)

    processed = _process(session, user, _text_document(session, user, tmp_path))

    assert processed.status == "failed"
    assert processed.processing_error is not None
    assert "longer than 0.05 seconds" in processed.processing_error


@pytest.mark.asyncio
async def test_a_run_stopped_by_shutdown_is_not_counted(
    session: Session, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(document_service, "extract_text_from_file", _slow_extract)
    user = _user(session)
    document = _text_document(session, user, tmp_path)
    assert user.id is not None and document.id is not None
    processor = DocumentProcessor()
    processor.schedule(user_id=user.id, document_id=document.id)
    await asyncio.sleep(0.05)

    await processor.shutdown()

    session.expire_all()
    interrupted = session.get(Document, document.id)
    assert interrupted is not None
    assert interrupted.status == "processing"
    assert interrupted.processing_attempts == 0


@pytest.mark.asyncio
async def test_startup_gives_up_on_a_document_after_repeated_crashes(
    session: Session, tmp_path
) -> None:
    user = _user(session)
    poison = _document(
        session,
        user,
        (tmp_path / "poison.pdf").as_posix(),
        "processing",
        processing_attempts=MAX_PROCESSING_ATTEMPTS,
    )
    retry = _document(
        session,
        user,
        (tmp_path / "retry.pdf").as_posix(),
        "processing",
        processing_attempts=MAX_PROCESSING_ATTEMPTS - 1,
    )
    resumed: list[int] = []

    def process(*, document_id: int, **_: Any) -> None:
        resumed.append(document_id)

    processor = DocumentProcessor(process=process)
    assert processor.resume_interrupted() == 1
    await processor.wait_idle()

    assert resumed == [retry.id]
    session.expire_all()
    given_up = session.get(Document, poison.id)
    assert given_up is not None
    assert given_up.status == "failed"
    assert given_up.processing_error == ATTEMPTS_EXHAUSTED_ERROR


async def _no_summary(**_: Any) -> None:
    return None


def _slow_extract(_: str) -> str:
    time.sleep(0.5)
    return "late text"
