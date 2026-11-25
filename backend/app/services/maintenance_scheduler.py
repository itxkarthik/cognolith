"""
Periodic housekeeping that keeps auth tables from growing without bound.

Every interval it deletes expired refresh tokens, access-token blacklist entries,
OAuth states and email verification codes. Each table is cleaned in its own
transaction so one failure does not block the others.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime

from sqlmodel import Session, col, delete

from app.core.database import engine
from app.models.backup import OAuthState
from app.models.user import EmailVerificationCode
from app.services.auth_service import cleanup_expired_tokens
from app.services.email_verification_service import SEND_WINDOW

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 6 * 60 * 60


def cleanup_expired_auth_records(session: Session, now: datetime | None = None) -> int:
    """Delete every expired auth record; returns the number of rows removed."""
    cutoff = now or datetime.now(UTC)
    removed = cleanup_expired_tokens(session)
    for statement in (
        delete(OAuthState).where(col(OAuthState.expires_at) < cutoff),
        # Keep a record while its send-rate window is open, or deleting it would
        # reset the per-hour resend limit
        delete(EmailVerificationCode).where(
            col(EmailVerificationCode.expires_at) < cutoff,
            col(EmailVerificationCode.window_started_at) < cutoff - SEND_WINDOW,
        ),
    ):
        result = session.exec(statement)
        removed += result.rowcount or 0
        session.commit()
    return removed


class MaintenanceScheduler:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session] | None = None,
        interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
    ) -> None:
        self.session_factory = session_factory or (lambda: Session(engine))
        self.interval_seconds = interval_seconds
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run_loop(), name="maintenance-scheduler")

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    def run_once(self) -> int:
        with self.session_factory() as session:
            return cleanup_expired_auth_records(session)

    async def _run_loop(self) -> None:
        while True:
            try:
                removed = await asyncio.to_thread(self.run_once)
                if removed:
                    logger.info("Removed %s expired auth records", removed)
            except Exception:
                logger.exception("Auth record cleanup did not complete")
            await asyncio.sleep(self.interval_seconds)
