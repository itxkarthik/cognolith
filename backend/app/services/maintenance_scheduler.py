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

from sqlalchemy import Delete
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, col, delete

from app.core.database import engine
from app.models.backup import OAuthState
from app.models.user import EmailVerificationCode, RefreshToken, TokenBlacklist
from app.services.email_verification_service import SEND_WINDOW

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 6 * 60 * 60


def _expired_record_deletes(cutoff: datetime) -> tuple[tuple[str, Delete], ...]:
    return (
        ("refresh tokens", delete(RefreshToken).where(col(RefreshToken.expires_at) < cutoff)),
        (
            "blacklist entries",
            delete(TokenBlacklist).where(col(TokenBlacklist.expires_at) < cutoff),
        ),
        ("OAuth states", delete(OAuthState).where(col(OAuthState.expires_at) < cutoff)),
        (
            "verification codes",
            # Keep a record while its send-rate window is open, or deleting it would
            # reset the per-hour resend limit
            delete(EmailVerificationCode).where(
                col(EmailVerificationCode.expires_at) < cutoff,
                col(EmailVerificationCode.window_started_at) < cutoff - SEND_WINDOW,
            ),
        ),
    )


def cleanup_expired_auth_records(session: Session, now: datetime | None = None) -> int:
    """
    Delete every expired auth record; returns the number of rows removed.
    Each table is its own transaction: a failure is rolled back and logged, and the
    remaining tables are still cleaned.
    """
    removed = 0
    for name, statement in _expired_record_deletes(now or datetime.now(UTC)):
        try:
            # Plain SQL delete: no need to sync (or compare dates on) loaded objects
            result = session.exec(statement.execution_options(synchronize_session=False))
            session.commit()
        except SQLAlchemyError:
            session.rollback()
            logger.exception("Cleaning up expired %s failed", name)
            continue
        removed += result.rowcount or 0
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
