"""
Per-chat-session generation guard and cancel signals, shared by the streaming,
non-streaming and WebSocket reply paths.

The backend runs as a single process, so the state lives in memory. The abstract
base keeps the contract separate from the storage: running several processes
would need an implementation backed by shared state (a Postgres advisory lock and
a cancel flag, or Redis), with no change to the callers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Generator
from contextlib import contextmanager
from threading import Event, Lock
from uuid import uuid4

from fastapi import HTTPException

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


class LocalGenerationCoordinator(GenerationCoordinator):
    def __init__(self) -> None:
        super().__init__()
        self._lock = Lock()
        self._by_session: dict[int, str] = {}

    def is_session_active(self, session_id: int) -> bool:
        with self._lock:
            return session_id in self._by_session

    def cancel(self, message_id: int) -> bool:
        return self._set_local_event(message_id)

    def _claim(self, *, session_id: int, token: str, message_id: int | None) -> bool:
        with self._lock:
            if session_id in self._by_session:
                return False
            self._by_session[session_id] = token
            return True

    def _release(self, *, session_id: int, token: str, message_id: int | None) -> None:
        with self._lock:
            if self._by_session.get(session_id) == token:
                self._by_session.pop(session_id, None)


generation_coordinator: GenerationCoordinator = LocalGenerationCoordinator()
