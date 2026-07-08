from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlmodel import Session

from app.core.config import settings
from app.models.user import EmailVerificationCode, User

CODE_TTL = timedelta(minutes=10)
RESEND_COOLDOWN = timedelta(seconds=60)
SEND_WINDOW = timedelta(hours=1)
MAX_SENDS_PER_WINDOW = 5
MAX_FAILED_ATTEMPTS = 5


class VerificationError(ValueError):
    pass


class InvalidVerificationCodeError(VerificationError):
    pass


class VerificationCodeExpiredError(VerificationError):
    pass


class VerificationRateLimitError(VerificationError):
    pass


@dataclass(frozen=True, slots=True)
class IssuedVerificationCode:
    code: str
    expires_at: datetime
    resend_available_at: datetime


def _require_user_id(user: User) -> int:
    if user.id is None:
        raise ValueError("User must be persisted before email verification")
    return user.id


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _hash_code(*, user_id: int, code: str) -> str:
    message = f"{user_id}:{code}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), message, hashlib.sha256).hexdigest()


def issue_verification_code(
    *, session: Session, user: User, now: datetime | None = None
) -> IssuedVerificationCode:
    user_id = _require_user_id(user)
    issued_at = _as_utc(now or datetime.now(UTC))
    record = session.get(EmailVerificationCode, user_id)

    if record is not None:
        if issued_at < _as_utc(record.resend_available_at):
            raise VerificationRateLimitError("Wait before requesting another code")
        window_started_at = _as_utc(record.window_started_at)
        if issued_at >= window_started_at + SEND_WINDOW:
            record.window_started_at = issued_at
            record.send_count = 0
        if record.send_count >= MAX_SENDS_PER_WINDOW:
            raise VerificationRateLimitError("Too many verification emails requested")

    code = f"{secrets.randbelow(1_000_000):06d}"
    expires_at = issued_at + CODE_TTL
    resend_available_at = issued_at + RESEND_COOLDOWN

    if record is None:
        record = EmailVerificationCode(
            user_id=user_id,
            code_hash=_hash_code(user_id=user_id, code=code),
            expires_at=expires_at,
            resend_available_at=resend_available_at,
            window_started_at=issued_at,
            send_count=1,
            updated_at=issued_at,
        )
    else:
        record.code_hash = _hash_code(user_id=user_id, code=code)
        record.expires_at = expires_at
        record.failed_attempts = 0
        record.resend_available_at = resend_available_at
        record.send_count += 1
        record.consumed_at = None
        record.updated_at = issued_at

    session.add(record)
    session.commit()
    return IssuedVerificationCode(
        code=code,
        expires_at=expires_at,
        resend_available_at=resend_available_at,
    )


def verify_email_code(
    *, session: Session, user: User, code: str, now: datetime | None = None
) -> None:
    user_id = _require_user_id(user)
    checked_at = _as_utc(now or datetime.now(UTC))
    record = session.get(EmailVerificationCode, user_id)
    if record is None or record.consumed_at is not None:
        raise InvalidVerificationCodeError("Invalid verification code")
    if checked_at > _as_utc(record.expires_at):
        raise VerificationCodeExpiredError("Verification code has expired")
    if record.failed_attempts >= MAX_FAILED_ATTEMPTS:
        raise InvalidVerificationCodeError("Verification code is locked")

    candidate = _hash_code(user_id=user_id, code=code)
    if not hmac.compare_digest(candidate, record.code_hash):
        record.failed_attempts += 1
        record.updated_at = checked_at
        session.add(record)
        session.commit()
        raise InvalidVerificationCodeError("Invalid verification code")

    record.consumed_at = checked_at
    record.updated_at = checked_at
    user.is_verified = True
    session.add(record)
    session.add(user)
    session.commit()
    session.refresh(user)


def mask_email(email: str) -> str:
    local, separator, domain = email.partition("@")
    if not separator:
        return email
    visible = local[:2] if len(local) > 2 else local[:1]
    return f"{visible}{'*' * max(3, len(local) - len(visible))}@{domain}"
