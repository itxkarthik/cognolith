"""Background document processing, queued in the documents table."""

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

# Scheduling


@pytest.fixture
def queued(session: Session):
    """Create `count` documents waiting in the queue; returns (user id, document ids)."""

    def create(count: int) -> tuple[int, list[int]]:
        user = crud.create_user(
            session=session,
            user_create=UserCreate(email="queue@example.com", password="secure-password"),
        )
        assert user.id is not None
        documents = [
            Document(
                user_id=user.id,
                title=f"Doc {index}",
                file_name="d.txt",
                file_path="/tmp/d.txt",
                file_size=1,
                file_type=".txt",
                mime_type="text/plain",
                status="processing",
            )
            for index in range(count)
        ]
        session.add_all(documents)
        session.commit()
        return user.id, [document.id for document in documents if document.id is not None]

    return create


def test_processing_is_limited_to_the_configured_concurrency(queued) -> None:
    user_id, document_ids = queued(5)
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
        for document_id in document_ids:
            processor.schedule(user_id=user_id, document_id=document_id)
        await processor.wait_idle()

    asyncio.run(scenario())

    assert peak == 2


def test_a_document_already_processing_is_not_scheduled_twice(queued) -> None:
    user_id, [document_id] = queued(1)
    calls: list[int] = []

    def process(*, document_id: int, **_: Any) -> None:
        calls.append(document_id)
        time.sleep(0.01)

    async def scenario() -> bool:
        processor = DocumentProcessor(process=process)
        assert processor.schedule(user_id=user_id, document_id=document_id) is True
        second = processor.schedule(user_id=user_id, document_id=document_id)
        await processor.wait_idle()
        return second

    assert asyncio.run(scenario()) is False
    assert calls == [document_id]


def test_a_failing_document_does_not_stop_the_others(queued) -> None:
    user_id, (broken, healthy) = queued(2)
    done: list[int] = []

    def process(*, document_id: int, **_: Any) -> None:
        if document_id == broken:
            raise RuntimeError("corrupt file")
        done.append(document_id)

    async def scenario() -> None:
        processor = DocumentProcessor(process=process)
        for document_id in (broken, healthy):
            processor.schedule(user_id=user_id, document_id=document_id)
        await processor.wait_idle()

    asyncio.run(scenario())

    assert done == [healthy]


def test_shutdown_stops_in_flight_processing_and_frees_the_document(
    session: Session, queued
) -> None:
    user_id, [document_id] = queued(1)
    events: list[str] = []

    def process(*, stop: threading.Event, **_: Any) -> None:
        deadline = time.monotonic() + 10
        while not stop.is_set() and time.monotonic() < deadline:
            time.sleep(0.01)
        events.append("stopped" if stop.is_set() else "ran to the end")
        raise ProcessingStoppedError

    async def scenario() -> None:
        processor = DocumentProcessor(process=process)
        processor.schedule(user_id=user_id, document_id=document_id)
        await asyncio.sleep(0.1)
        await processor.shutdown()
        # Returned only once the run had stopped
        assert events == ["stopped"]

    asyncio.run(scenario())

    session.expire_all()
    stopped = session.get(Document, document_id)
    assert stopped is not None
    # Free for any process to resume at once
    assert (stopped.status, stopped.processing_lease_until) == ("processing", None)


def test_processing_runs_off_the_event_loop(queued) -> None:
    user_id, [document_id] = queued(1)
    gaps: list[float] = []

    def process(**_: Any) -> None:
        time.sleep(0.3)  # file parsing, database writes, model calls

    async def scenario() -> None:
        processor = DocumentProcessor(process=process)
        processor.schedule(user_id=user_id, document_id=document_id)
        last = time.perf_counter()
        for _ in range(20):
            await asyncio.sleep(0.01)
            now = time.perf_counter()
            gaps.append(now - last)
            last = now
        await processor.wait_idle()

    asyncio.run(scenario())

    assert max(gaps) < 0.1


# Several processes (issue #29): two processors stand in for two processes


def test_a_document_is_processed_by_one_process_only(queued) -> None:
    user_id, document_ids = queued(4)
    runs: list[tuple[str, int]] = []
    lock = threading.Lock()

    def processing(name: str):
        def process(*, document_id: int, **_: Any) -> None:
            with lock:
                runs.append((name, document_id))
            time.sleep(0.05)

        return process

    async def scenario() -> None:
        first = DocumentProcessor(process=processing("first"))
        second = DocumentProcessor(process=processing("second"))
        # Both see every waiting document, as their pollers would
        for document_id in document_ids:
            first.schedule(user_id=user_id, document_id=document_id)
            second.schedule(user_id=user_id, document_id=document_id)
        await asyncio.gather(first.wait_idle(), second.wait_idle())

    asyncio.run(scenario())

    assert sorted(document_id for _, document_id in runs) == sorted(document_ids)


def test_a_crashed_processs_document_is_picked_up_after_its_lease(session: Session, queued) -> None:
    user_id, [document_id] = queued(1)
    # A process claimed it, then died without freeing it
    document = session.get(Document, document_id)
    assert document is not None
    session.connection().exec_driver_sql(
        "UPDATE documents SET processing_lease_until = now() + interval '1 minute'"
    )
    session.commit()
    runs: list[int] = []

    def process(*, document_id: int, **_: Any) -> None:
        runs.append(document_id)

    async def scenario() -> tuple[int, int]:
        processor = DocumentProcessor(process=process)
        while_held = await processor.schedule_waiting()
        session.connection().exec_driver_sql(
            "UPDATE documents SET processing_lease_until = now() - interval '1 second'"
        )
        session.commit()
        after_expiry = await processor.schedule_waiting()
        await processor.wait_idle()
        return while_held, after_expiry

    assert asyncio.run(scenario()) == (0, 1)
    assert runs == [document_id]


def test_the_poller_picks_up_another_processs_upload(queued) -> None:
    user_id, [document_id] = queued(1)  # uploaded through another process
    runs: list[int] = []

    def process(*, session: Session, document_id: int, **_: Any) -> None:
        runs.append(document_id)
        document = session.get(Document, document_id)
        assert document is not None
        document.status = "completed"  # as real processing ends it
        session.add(document)
        session.commit()

    async def scenario() -> None:
        processor = DocumentProcessor(process=process, poll_seconds=0.02)
        await processor.start()
        await asyncio.sleep(0.1)
        await processor.wait_idle()
        await processor.shutdown()

    asyncio.run(scenario())
    # Polled several times, processed once
    assert runs == [document_id]
    del user_id


def test_runs_waiting_for_a_slot_do_not_start_after_shutdown(session: Session, queued) -> None:
    user_id, (running, waiting) = queued(2)
    started: list[int] = []

    def process(*, document_id: int, stop: threading.Event, **_: Any) -> None:
        started.append(document_id)
        while not stop.wait(0.01):
            pass
        raise ProcessingStoppedError

    async def scenario() -> bool:
        processor = DocumentProcessor(concurrency=1, process=process)
        processor.schedule(user_id=user_id, document_id=running)
        processor.schedule(user_id=user_id, document_id=waiting)
        await asyncio.sleep(0.1)
        await processor.shutdown()
        return processor.schedule(user_id=user_id, document_id=waiting)

    assert asyncio.run(scenario()) is False
    assert started == [running]
    session.expire_all()
    left = session.get(Document, waiting)
    assert left is not None
    assert (left.status, left.processing_lease_until) == ("processing", None)


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
    assert await processor.schedule_waiting() == 1
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


def test_the_indexer_reindexes_a_failed_document(session: Session, tmp_path, monkeypatch) -> None:
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
    assert await processor.schedule_waiting() == 1
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


@pytest.mark.asyncio
async def test_a_run_that_lost_its_lease_stops_counted_and_leaves_the_new_holder(
    session: Session, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(document_service, "extract_text_from_file", _slow_extract)
    user = _user(session)
    document = _text_document(session, user, tmp_path)
    assert user.id is not None and document.id is not None
    # Renews every 0.1 s
    processor = DocumentProcessor(lease_seconds=0.3)
    processor.schedule(user_id=user.id, document_id=document.id)
    await asyncio.sleep(0.05)
    # The process stalled past its lease and another one claimed the document
    session.connection().exec_driver_sql(
        "UPDATE documents SET processing_lease_token = 'other', "
        "processing_lease_until = now() + interval '1 minute'"
    )
    session.commit()

    await asyncio.wait_for(processor.wait_idle(), timeout=5)

    session.expire_all()
    stalled = session.get(Document, document.id)
    assert stalled is not None
    # Stopped before finishing, without touching the new holder's lease
    assert stalled.status == "processing"
    assert stalled.processing_lease_token == "other"
    # A process that stalls on a file uses up an attempt
    assert stalled.processing_attempts == 1
