"""
Background processing of uploaded documents, shared by every backend process.

An upload stores the file, saves the document with status "processing" and returns;
extraction, embedding and the summary then run here, at most
DOCUMENT_PROCESSING_CONCURRENCY at a time per process, while the client polls the
status. Each run is blocking work (file parsing, database writes, model calls), so
it runs in a worker thread and the event loop stays free for requests.

The documents table is the queue. A process claims a document with a lease row in
`document_processing_leases` (a fresh token, an expiry) and renews it while the run
lasts, so no two processes run the same document. A process that stalls past its
lease loses the document: its renewal finds another token, and the run stops at its
next step. Leases live apart from the documents row, which a run keeps write-locked
through its model calls, so claiming and renewing never wait for a run. Every process polls for documents still
"processing" whose lease is missing or expired: new uploads (whichever process
received them), and documents of a process that crashed or was stopped. That is
safe because processing resets the document first. Shutdown asks in-flight runs to
stop at their next step, waits for them and frees their leases without counting
the interrupted run.

Each run counts an attempt before it starts. A file that crashes or hangs the
process is therefore retried MAX_PROCESSING_ATTEMPTS times at most, then failed.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from contextlib import suppress
from threading import Event
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlmodel import Session

from app.core.config import settings
from app.core.database import engine

logger = logging.getLogger(__name__)

# Called in a worker thread as process(session=, user_id=, document_id=, stop=)
ProcessFunction = Callable[..., Any]

MAX_PROCESSING_ATTEMPTS = 3
ATTEMPTS_EXHAUSTED_ERROR = (
    f"Processing stopped after {MAX_PROCESSING_ATTEMPTS} interrupted attempts. "
    "The file may be too large or malformed; upload it again to retry."
)
# A crashed process's documents are picked up this long after its last renewal
PROCESSING_LEASE_SECONDS = 60.0
POLL_SECONDS = 5.0

# Documents waiting for a process: no lease, or one whose holder stopped renewing it
_CLAIMABLE = """
    d.status = 'processing'
    AND d.is_deleted = false
    AND NOT EXISTS (
        SELECT 1 FROM document_processing_leases l
        WHERE l.document_id = d.id AND l.lease_until >= now()
    )
"""


class ProcessingStoppedError(Exception):
    """The run was asked to stop at its next step."""


class StopRequest(Event):
    """
    Set to stop a run. A shutdown says nothing about the file, so that run isn't
    counted; a lost lease is (the process stalled, maybe on this file), and the
    document now belongs to another process, so it's left alone.
    """

    def __init__(self) -> None:
        super().__init__()
        self.lease_lost = False
        # The run's lease, once claimed; None for a run outside the queue
        self.lease_token: str | None = None

    def stop_for_lost_lease(self) -> None:
        self.lease_lost = True
        self.set()

    def holds_lease(self, session: Session, document_id: int) -> bool:
        """
        Lock this run's lease in `session`'s transaction, so no process can take the
        document over until that transaction ends. False, and stopped, if another
        process has it now. Lock the document row first: every process takes the
        two in that order, so they can't deadlock.
        """
        if self.lease_token is None:
            return True
        held = session.connection().execute(
            text(
                "SELECT 1 FROM document_processing_leases "
                "WHERE document_id = :document_id AND token = :token FOR UPDATE"
            ),
            {"document_id": document_id, "token": self.lease_token},
        )
        if held.first() is None:
            self.stop_for_lost_lease()
            return False
        return True


def _process_existing_document(**kwargs: Any) -> Any:
    # Imported here: document_service schedules work on this module's processor
    from app.services.document_service import process_existing_document

    return process_existing_document(**kwargs)


class DocumentProcessor:
    def __init__(
        self,
        *,
        concurrency: int | None = None,
        process: ProcessFunction | None = None,
        lease_seconds: float = PROCESSING_LEASE_SECONDS,
        poll_seconds: float = POLL_SECONDS,
    ) -> None:
        self._concurrency = concurrency or settings.DOCUMENT_PROCESSING_CONCURRENCY
        self._process = process or _process_existing_document
        self._lease = lease_seconds
        self._poll = poll_seconds
        self._tasks: dict[int, asyncio.Task[None]] = {}
        self._stops: dict[int, StopRequest] = {}
        self._semaphore: asyncio.Semaphore | None = None
        self._semaphore_loop: asyncio.AbstractEventLoop | None = None
        self._poller: asyncio.Task[None] | None = None
        self._closing = False

    def schedule(self, *, user_id: int, document_id: int) -> bool:
        """
        Process the document in the background unless this process already is.
        The run claims it first, so it's skipped if another process has it.
        """
        if self._closing:
            return False  # left for whichever process runs next
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

    async def start(self) -> None:
        """Pick up waiting documents now, then keep polling for them."""
        self._closing = False
        await self.schedule_waiting()
        if self._poller is None or self._poller.done():
            self._poller = asyncio.create_task(self._poll_loop(), name="document-poller")

    async def schedule_waiting(self) -> int:
        """Schedule every unclaimed "processing" document; returns how many were new."""
        waiting = await asyncio.to_thread(self._waiting_documents)
        return sum(
            self.schedule(user_id=user_id, document_id=document_id)
            for document_id, user_id in waiting
        )

    async def wait_idle(self) -> None:
        """Wait until all scheduled processing has finished (tests, graceful stops)."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks.values()), return_exceptions=True)

    async def shutdown(self) -> None:
        """
        Stop in-flight runs at their next step and wait for them; their documents
        are freed for any process to resume. Runs still waiting for a slot don't start.
        """
        self._closing = True
        if self._poller is not None:
            self._poller.cancel()
            with suppress(asyncio.CancelledError):
                await self._poller
            self._poller = None
        for stop in list(self._stops.values()):
            stop.set()
        await asyncio.gather(*list(self._tasks.values()), return_exceptions=True)

    async def _poll_loop(self) -> None:
        while True:
            await asyncio.sleep(self._poll)
            try:
                await self.schedule_waiting()
            except Exception:
                logger.exception("Polling for documents to process failed")

    async def _run(self, *, user_id: int, document_id: int) -> None:
        stop = self._stops.setdefault(document_id, StopRequest())
        try:
            # The slot comes first: a lease is only taken when the run can start,
            # so it never lapses while waiting
            async with self._limit():
                if self._closing or stop.is_set():
                    return
                token = uuid4().hex
                if not await asyncio.to_thread(self._claim, document_id, token):
                    return
                stop.lease_token = token
                renewing = asyncio.create_task(self._renew_lease(document_id, token, stop))
                try:
                    # Shielded: a cancelled task can't stop the thread, which must still
                    # see the stop request and leave the document as it should be
                    await asyncio.shield(
                        asyncio.to_thread(
                            self._run_in_thread,
                            user_id=user_id,
                            document_id=document_id,
                            stop=stop,
                        )
                    )
                finally:
                    renewing.cancel()
                    # In a thread, off the loop; shielded, so the lease is freed even
                    # if this task is cancelled meanwhile
                    await asyncio.shield(asyncio.to_thread(self._release, document_id, token))
        finally:
            self._stops.pop(document_id, None)

    def _run_in_thread(self, *, user_id: int, document_id: int, stop: StopRequest) -> None:
        try:
            with Session(engine) as session:
                self._process(session=session, user_id=user_id, document_id=document_id, stop=stop)
        except ProcessingStoppedError:
            return  # shutdown; any process resumes it
        except Exception:
            # The document is marked failed with the reason; nothing to propagate
            logger.exception(
                "Background document processing failed",
                extra={"document_id": document_id, "user_id": user_id},
            )

    async def _renew_lease(self, document_id: int, token: str, stop: StopRequest) -> None:
        while True:
            await asyncio.sleep(self._lease / 3)
            try:
                if not await asyncio.to_thread(self._extend, document_id, token):
                    logger.warning(
                        "Lost the lease on a document; another process runs it now",
                        extra={"document_id": document_id},
                    )
                    stop.stop_for_lost_lease()
                    return
            except Exception:
                # Retried on the next tick; the lease allows two misses
                logger.exception(
                    "Could not renew a document lease", extra={"document_id": document_id}
                )

    def _waiting_documents(self) -> list[tuple[int, int]]:
        """Fail documents out of attempts; return (id, user id) of the others waiting."""
        with engine.begin() as connection:
            exhausted = connection.execute(
                text(
                    f"""
                    UPDATE documents AS d SET
                        status = 'failed',
                        processing_error = :error,
                        processing_completed_at = timezone('utc', now())
                    WHERE {_CLAIMABLE} AND d.processing_attempts >= :max_attempts
                    RETURNING d.id, d.processing_attempts
                    """
                ),
                {"error": ATTEMPTS_EXHAUSTED_ERROR, "max_attempts": MAX_PROCESSING_ATTEMPTS},
            ).all()
            for row in exhausted:
                logger.warning(
                    "Gave up processing a document after repeated interruptions",
                    extra={"document_id": row.id, "attempts": row.processing_attempts},
                )
            rows = connection.execute(
                text(f"SELECT d.id, d.user_id FROM documents d WHERE {_CLAIMABLE} ORDER BY d.id")
            ).all()
        return [(int(row.id), int(row.user_id)) for row in rows]

    def _claim(self, document_id: int, token: str) -> bool:
        # Only a waiting document, and only over an expired lease: a concurrent
        # claim of the same document waits for this one and then finds it live
        return self._update_lease(
            f"""
            INSERT INTO document_processing_leases (document_id, token, lease_until)
            SELECT d.id, :token, now() + make_interval(secs => :lease)
            FROM documents d
            WHERE d.id = :document_id AND {_CLAIMABLE}
            ON CONFLICT (document_id) DO UPDATE SET
                token = EXCLUDED.token,
                lease_until = EXCLUDED.lease_until
            WHERE document_processing_leases.lease_until < now()
            RETURNING document_id
            """,
            document_id,
            token,
        )

    def _extend(self, document_id: int, token: str) -> bool:
        """False when the lease is no longer this run's."""
        return self._update_lease(
            """
            UPDATE document_processing_leases
            SET lease_until = now() + make_interval(secs => :lease)
            WHERE document_id = :document_id AND token = :token
            RETURNING document_id
            """,
            document_id,
            token,
        )

    def _release(self, document_id: int, token: str) -> None:
        try:
            self._update_lease(
                """
                DELETE FROM document_processing_leases
                WHERE document_id = :document_id AND token = :token
                RETURNING document_id
                """,
                document_id,
                token,
            )
        except Exception:
            # The lease expires on its own
            logger.exception("Could not free a document lease", extra={"document_id": document_id})

    def _update_lease(self, statement: str, document_id: int, token: str) -> bool:
        with engine.begin() as connection:
            row = connection.execute(
                text(statement),
                {"document_id": document_id, "token": token, "lease": self._lease},
            ).first()
        return row is not None

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
