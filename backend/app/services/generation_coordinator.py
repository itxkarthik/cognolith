"""
Per-chat-session generation guard and cancel signals, shared by the streaming,
non-streaming and WebSocket reply paths.

Claims live in Postgres so they hold across backend processes: at most one reply is
generated per chat session, and a cancel request reaches the process generating
the reply whichever process receives it. The abstract base keeps that contract
apart from the storage.
"""

from __future__ import annotations

import logging
import os
import socket
import time
from abc import ABC, abstractmethod
from collections.abc import Generator
from contextlib import contextmanager
from threading import Event, Lock, Thread
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import text

from app.core.database import engine

logger = logging.getLogger(__name__)

BUSY_DETAIL = "A reply is already being generated for this chat session."


class GenerationCoordinator(ABC):
    def __init__(self) -> None:
        self._events_lock = Lock()
        # Cancel events for the replies this process is generating
        self._events: dict[int, Event] = {}

    def start(self, *, session_id: int, message_id: int) -> Event:
        """Claim the session for a streamed reply; raise 409 if one is running."""
        if not self._claim(session_id=session_id, token=str(message_id), message_id=message_id):
            raise HTTPException(status_code=409, detail=BUSY_DETAIL)
        event = Event()
        with self._events_lock:
            self._events[message_id] = event
        return event

    @contextmanager
    def exclusive(self, *, session_id: int) -> Generator[None, None, None]:
        """Hold the session for a whole non-streaming generation, or raise 409."""
        token = f"reserved:{uuid4().hex}"
        if not self._claim(session_id=session_id, token=token, message_id=None):
            raise HTTPException(status_code=409, detail=BUSY_DETAIL)
        try:
            yield
        finally:
            self._release(session_id=session_id, token=token, message_id=None)

    def finish(self, *, session_id: int, message_id: int) -> None:
        with self._events_lock:
            self._events.pop(message_id, None)
        self._release(session_id=session_id, token=str(message_id), message_id=message_id)

    def _set_local_event(self, message_id: int) -> bool:
        with self._events_lock:
            event = self._events.get(message_id)
        if event is None:
            return False
        event.set()
        return True

    @abstractmethod
    def is_session_active(self, session_id: int) -> bool: ...

    @abstractmethod
    def cancel(self, message_id: int) -> bool:
        """Ask the process generating this reply to stop; False if none is."""

    @abstractmethod
    def _claim(self, *, session_id: int, token: str, message_id: int | None) -> bool: ...

    @abstractmethod
    def _release(self, *, session_id: int, token: str, message_id: int | None) -> None: ...


# A claim is live while its holder's heartbeat is newer than this
CLAIM_LEASE_SECONDS = 30.0
HEARTBEAT_SECONDS = 2.0

_LIVE = "heartbeat_at >= now() - make_interval(secs => :lease)"


class PostgresGenerationCoordinator(GenerationCoordinator):
    """
    Claims and cancel requests in the `chat_generation_claims` table, so every
    backend process sees them. A background thread renews this process's claims and
    relays cancel requests made through another process to the local events.
    """

    def __init__(
        self,
        *,
        lease_seconds: float = CLAIM_LEASE_SECONDS,
        heartbeat_seconds: float = HEARTBEAT_SECONDS,
    ) -> None:
        super().__init__()
        self._lease = lease_seconds
        self._heartbeat = heartbeat_seconds
        self.owner = f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex[:8]}"
        self._held_lock = Lock()
        # session id -> (token, message id) of the claims this process holds
        self._held: dict[int, tuple[str, int | None]] = {}
        self._beat_lock = Lock()
        self._beating: Thread | None = None

    def is_session_active(self, session_id: int) -> bool:
        with engine.connect() as connection:
            return bool(
                connection.execute(
                    text(
                        "SELECT EXISTS (SELECT 1 FROM chat_generation_claims "
                        f"WHERE session_id = :session_id AND {_LIVE})"
                    ),
                    {"session_id": session_id, "lease": self._lease},
                ).scalar_one()
            )

    def cancel(self, message_id: int) -> bool:
        local = self._set_local_event(message_id)
        with engine.begin() as connection:
            flagged = connection.execute(
                text(
                    "UPDATE chat_generation_claims SET cancel_requested = true "
                    f"WHERE message_id = :message_id AND {_LIVE} RETURNING session_id"
                ),
                {"message_id": message_id, "lease": self._lease},
            ).first()
        return local or flagged is not None

    def _claim(self, *, session_id: int, token: str, message_id: int | None) -> bool:
        with engine.begin() as connection:
            # Takes the session when it's free or its holder stopped renewing
            claimed = connection.execute(
                text(
                    """
                    INSERT INTO chat_generation_claims
                        (session_id, token, message_id, owner, heartbeat_at, cancel_requested)
                    VALUES (:session_id, :token, :message_id, :owner, now(), false)
                    ON CONFLICT (session_id) DO UPDATE SET
                        token = EXCLUDED.token,
                        message_id = EXCLUDED.message_id,
                        owner = EXCLUDED.owner,
                        heartbeat_at = now(),
                        cancel_requested = false
                    WHERE chat_generation_claims.heartbeat_at
                        < now() - make_interval(secs => :lease)
                    RETURNING session_id
                    """
                ),
                {
                    "session_id": session_id,
                    "token": token,
                    "message_id": message_id,
                    "owner": self.owner,
                    "lease": self._lease,
                },
            ).first()
        if claimed is None:
            return False
        with self._held_lock:
            self._held[session_id] = (token, message_id)
        self._ensure_heartbeat()
        return True

    def _release(self, *, session_id: int, token: str, message_id: int | None) -> None:
        with self._held_lock:
            if self._held.get(session_id, (None, None))[0] == token:
                del self._held[session_id]
        with engine.begin() as connection:
            connection.execute(
                text(
                    "DELETE FROM chat_generation_claims "
                    "WHERE session_id = :session_id AND token = :token"
                ),
                {"session_id": session_id, "token": token},
            )

    def renew(self) -> None:
        """
        Refresh this process's claims and pass on cancel requests. A claim that's
        gone was taken over (this process looked dead), so its reply stops too.
        """
        with self._held_lock:
            held = dict(self._held)
        if not held:
            return
        with engine.begin() as connection:
            rows = connection.execute(
                text(
                    """
                    UPDATE chat_generation_claims SET heartbeat_at = now()
                    WHERE (session_id, token) IN (
                        SELECT * FROM unnest(CAST(:session_ids AS int[]), CAST(:tokens AS text[]))
                    )
                    RETURNING session_id, cancel_requested
                    """
                ),
                {
                    "session_ids": list(held),
                    "tokens": [token for token, _ in held.values()],
                },
            ).all()
        renewed = {row.session_id: row.cancel_requested for row in rows}
        for session_id, (token, message_id) in held.items():
            if session_id not in renewed:
                # Taken over or deleted as dead: no longer this process's to renew
                with self._held_lock:
                    if self._held.get(session_id, (None, None))[0] == token:
                        del self._held[session_id]
            if message_id is not None and renewed.get(session_id, True):
                self._set_local_event(message_id)

    def _ensure_heartbeat(self) -> None:
        with self._beat_lock:
            if self._beating is None or not self._beating.is_alive():
                self._beating = Thread(
                    target=self._beat, name="generation-claims-heartbeat", daemon=True
                )
                self._beating.start()

    def _beat(self) -> None:
        while True:
            time.sleep(self._heartbeat)
            try:
                self.renew()
            except Exception:
                # Retried on the next beat; the lease allows several misses
                logger.exception("Could not renew chat generation claims")


generation_coordinator: GenerationCoordinator = PostgresGenerationCoordinator()
