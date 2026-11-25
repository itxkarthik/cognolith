"""Background document processing inside the API process."""

import asyncio
from io import BytesIO
from typing import Any

import pytest
from fastapi import UploadFile
from sqlmodel import Session

from app import crud
from app.core.config import settings
from app.models.document import Document
from app.models.user import User, UserCreate
from app.services import document_service
from app.services.document_processing import DocumentProcessor, document_processor

# Scheduling (no database)


def test_processing_is_limited_to_the_configured_concurrency() -> None:
    running = 0
    peak = 0

    async def process(**_: Any) -> None:
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.02)
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

    async def process(*, document_id: int, **_: Any) -> None:
        calls.append(document_id)
        await asyncio.sleep(0.01)

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

    async def process(*, document_id: int, **_: Any) -> None:
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


def test_shutdown_cancels_in_flight_processing() -> None:
    events: list[str] = []

    async def process(**_: Any) -> None:
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            events.append("cancelled")
            raise

    async def scenario() -> None:
        processor = DocumentProcessor(process=process)
        processor.schedule(user_id=1, document_id=1)
        await asyncio.sleep(0.01)
        await processor.shutdown()

    asyncio.run(scenario())

    assert events == ["cancelled"]


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
        session=session,
        current_user=user,
        file=UploadFile(filename="atlas.txt", file=BytesIO(b"The Atlas launch window is Friday morning.")),
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

    async def process(*, document_id: int, **_: Any) -> None:
        resumed.append(document_id)

    processor = DocumentProcessor(process=process)
    assert processor.resume_interrupted() == 1
    await processor.wait_idle()

    assert resumed == [interrupted.id]
