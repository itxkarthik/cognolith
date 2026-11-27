"""
Embed new and changed workspace content in the background (issue #24).

Chat and search only read vectors. A commit that writes a note or document marks its
owner here (a Session hook, so every write path is covered), as does a finished
chat reply. After a short debounce the user's workspace is brought up to date by
`ensure_workspace_embeddings`, in a worker thread with its own session.

A transaction-scoped advisory lock per user keeps two processes from indexing the
same workspace at once; the one that doesn't get it tries again later. A failed run
(the embedding model down, say) is retried after RETRY_SECONDS, and startup marks
every user, which catches up on anything a restart interrupted.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from threading import Lock
from typing import Any

from sqlalchemy import event, func
from sqlmodel import Session, select

from app.ai.embeddings import resolve_embedding_model
from app.ai.rag import ensure_workspace_embeddings
from app.ai.vectorstore import PgVectorStore
from app.core.database import engine
from app.models.chat import ChatSession
from app.models.document import Document
from app.models.note import Notes
from app.models.user import User

logger = logging.getLogger(__name__)

# Wait this long after a change, so a burst of saves is indexed once
DEBOUNCE_SECONDS = 2.0
RETRY_SECONDS = 60.0
POLL_SECONDS = 0.5
# Advisory lock class for "indexing this user's workspace" ("INDX")
INDEX_LOCK_CLASS = 0x494E4458

# Index one user's workspace; False when it couldn't run now and should be retried
IndexUser = Callable[[int], bool]


def index_user_workspace(user_id: int) -> bool:
    """Embed everything of the user's that has no current vector. Blocking."""
    with Session(engine) as session:
        locked = session.exec(
            select(func.pg_try_advisory_xact_lock(INDEX_LOCK_CLASS, user_id))
        ).one()
        if not locked:
            return False  # another process is indexing this user
        ensure_workspace_embeddings(
            session=session,
            vector_store=PgVectorStore(session=session),
            user_id=user_id,
            embedding_model=resolve_embedding_model(session=session, user_id=user_id),
            include_chats=True,
        )
        session.commit()  # also releases the lock
    return True


class WorkspaceIndexer:
    def __init__(
        self,
        *,
        index_user: IndexUser | None = None,
        debounce_seconds: float = DEBOUNCE_SECONDS,
        retry_seconds: float = RETRY_SECONDS,
        poll_seconds: float = POLL_SECONDS,
    ) -> None:
        self._index_user = index_user or index_user_workspace
        self._debounce = debounce_seconds
        self._retry = retry_seconds
        self._poll = poll_seconds
        self._lock = Lock()
        # user id -> monotonic time the user is due for indexing
        self._due: dict[int, float] = {}
        self._task: asyncio.Task[None] | None = None

    def mark_dirty(self, user_id: int, *, delay: float | None = None) -> None:
        """Index the user's workspace soon. Thread-safe; called from worker threads."""
        due = time.monotonic() + (self._debounce if delay is None else delay)
        with self._lock:
            # A change while already waiting keeps the earlier time, so a stream of
            # saves can't postpone indexing indefinitely
            self._due[user_id] = min(due, self._due.get(user_id, due))

    def pending(self) -> set[int]:
        with self._lock:
            return set(self._due)

    async def start(self) -> None:
        """Catch up every user (a restart may have interrupted indexing), then run."""
        user_ids = await asyncio.to_thread(_all_user_ids)
        for user_id in user_ids:
            self.mark_dirty(user_id)
        self._task = asyncio.create_task(self._run(), name="workspace-indexer")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def run_due(self) -> None:
        """Index every user whose time has come, one at a time."""
        while (user_id := self._take_due()) is not None:
            try:
                indexed = await asyncio.to_thread(self._index_user, user_id)
            except Exception:
                logger.exception("Workspace indexing failed", extra={"user_id": user_id})
                indexed = False
                self.mark_dirty(user_id, delay=self._retry)
                continue
            if not indexed:
                self.mark_dirty(user_id)

    async def _run(self) -> None:
        while True:
            await self.run_due()
            await asyncio.sleep(self._poll)

    def _take_due(self) -> int | None:
        now = time.monotonic()
        with self._lock:
            for user_id, due in self._due.items():
                if due <= now:
                    del self._due[user_id]
                    return user_id
        return None


def _all_user_ids() -> list[int]:
    with Session(engine) as session:
        return [user_id for user_id in session.exec(select(User.id)).all() if user_id is not None]


workspace_indexer = WorkspaceIndexer()

# --- marking owners on commit ------------------------------------------------------

_PENDING_KEY = "workspace_indexer_users"
# Rows whose writes change what gets embedded. A chat message has no user id, but
# sending one updates its session; a streamed reply's final write is a bulk UPDATE,
# so the stream marks its owner itself.
_INDEXED_MODELS = (Notes, Document, ChatSession)


def _collect_owners(session: Any, _flush_context: Any) -> None:
    owners: set[int] = session.info.setdefault(_PENDING_KEY, set())
    for instance in (*session.new, *session.dirty, *session.deleted):
        if isinstance(instance, _INDEXED_MODELS) and instance.user_id is not None:
            owners.add(instance.user_id)


def _mark_owners(session: Any) -> None:
    for user_id in session.info.pop(_PENDING_KEY, ()):
        workspace_indexer.mark_dirty(user_id)


event.listen(Session, "after_flush", _collect_owners)
# Owners collected before a rollback stay pending: an extra mark only costs a run
# that finds nothing to embed, a lost one leaves content unsearchable
event.listen(Session, "after_commit", _mark_owners)
