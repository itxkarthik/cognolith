"""
Background processing of uploaded documents inside the API process.

An upload stores the file, saves the document with status "processing" and returns;
extraction, embedding and the summary then run here as asyncio tasks, at most
DOCUMENT_PROCESSING_CONCURRENCY at a time, while the client polls the status.

The documents table is the durable record: a document still "processing" at startup
was interrupted by a restart or crash and is processed again. That is safe because
processing resets the document first. Shutdown cancels in-flight work, leaving those
documents to be resumed on the next start.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from sqlmodel import Session, col, select

from app.core.config import settings
from app.core.database import engine
from app.models.document import Document

logger = logging.getLogger(__name__)

ProcessFunction = Callable[..., Awaitable[Any]]


async def _process_existing_document(**kwargs: Any) -> Any:
    # Imported here: document_service schedules work on this module's processor
    from app.services.document_service import process_existing_document

    return await process_existing_document(**kwargs)


class DocumentProcessor:
    def __init__(
        self,
        *,
        concurrency: int | None = None,
        process: ProcessFunction | None = None,
    ) -> None:
        self._concurrency = concurrency or settings.DOCUMENT_PROCESSING_CONCURRENCY
        self._process = process or _process_existing_document
        self._tasks: dict[int, asyncio.Task[None]] = {}
        self._semaphore: asyncio.Semaphore | None = None
        self._semaphore_loop: asyncio.AbstractEventLoop | None = None

    def schedule(self, *, user_id: int, document_id: int) -> bool:
        """Start processing in the background; False if this document is already running."""
        existing = self._tasks.get(document_id)
        if existing is not None and not existing.done():
            return False
        task = asyncio.get_running_loop().create_task(
            self._run(user_id=user_id, document_id=document_id),
            name=f"process-document-{document_id}",
        )
        self._tasks[document_id] = task
        task.add_done_callback(lambda done: self._forget(document_id, done))
        return True

    def resume_interrupted(self) -> int:
        """Schedule every document left in "processing" by a previous run."""
        with Session(engine) as session:
            rows = session.exec(
                select(Document.id, Document.user_id).where(
                    Document.status == "processing",
                    col(Document.is_deleted).is_(False),
                )
            ).all()
        resumed = 0
        for document_id, user_id in rows:
            if document_id is None or user_id is None:
                continue
            if self.schedule(user_id=user_id, document_id=document_id):
                resumed += 1
        return resumed

    async def wait_idle(self) -> None:
        """Wait until all scheduled processing has finished (tests, graceful stops)."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks.values()), return_exceptions=True)

    async def shutdown(self) -> None:
        """Cancel in-flight work; those documents stay "processing" and resume on start."""
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _run(self, *, user_id: int, document_id: int) -> None:
        async with self._limit():
            try:
                with Session(engine) as session:
                    await self._process(session=session, user_id=user_id, document_id=document_id)
            except Exception:
                # The document is marked failed with the reason; nothing to propagate
                logger.exception(
                    "Background document processing failed",
                    extra={"document_id": document_id, "user_id": user_id},
                )

    def _limit(self) -> asyncio.Semaphore:
        # A semaphore belongs to one event loop; tests run several loops in turn
        loop = asyncio.get_running_loop()
        if self._semaphore is None or self._semaphore_loop is not loop:
            self._semaphore = asyncio.Semaphore(self._concurrency)
            self._semaphore_loop = loop
        return self._semaphore

    def _forget(self, document_id: int, task: asyncio.Task[None]) -> None:
        if self._tasks.get(document_id) is task:
            del self._tasks[document_id]


document_processor = DocumentProcessor()
