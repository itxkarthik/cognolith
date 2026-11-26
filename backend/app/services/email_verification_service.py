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


def _hash_code(*, user_id: int, code: str, address: str | None) -> str:
    # An email-change code is bound to the address it was sent to, so it can't
    # confirm a different pending address. Signup codes keep the original format.
    message = (f"{user_id}:{code}" if address is None else f"{user_id}:{address}:{code}").encode()
    return hmac.new(settings.SECRET_KEY.encode(), message, hashlib.sha256).hexdigest()


def issue_verification_code(
    *, session: Session, user: User, now: datetime | None = None, address: str | None = None
) -> IssuedVerificationCode:
    """Issue a new code for the user; pass `address` to bind it to an email change."""
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
            code_hash=_hash_code(user_id=user_id, code=code, address=address),
            expires_at=expires_at,
            resend_available_at=resend_available_at,
            window_started_at=issued_at,
            send_count=1,
            updated_at=issued_at,
        )
    else:
        record.code_hash = _hash_code(user_id=user_id, code=code, address=address)
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


def check_verification_code(
    *,
    session: Session,
    user: User,
    code: str,
    now: datetime | None = None,
    address: str | None = None,
) -> None:
    """
    Consume the user's current code, or raise. Failed attempts are counted and
    committed; on success the consumption is staged for the caller's commit.
    An email-change code only matches the `address` it was issued for.
    """
    user_id = _require_user_id(user)
    checked_at = _as_utc(now or datetime.now(UTC))
    record = session.get(EmailVerificationCode, user_id)
    if record is None or record.consumed_at is not None:
        raise InvalidVerificationCodeError("Invalid verification code")
    if checked_at > _as_utc(record.expires_at):
        raise VerificationCodeExpiredError("Verification code has expired")
    if record.failed_attempts >= MAX_FAILED_ATTEMPTS:
        raise InvalidVerificationCodeError("Verification code is locked")

    candidate = _hash_code(user_id=user_id, code=code, address=address)
    if not hmac.compare_digest(candidate, record.code_hash):
        record.failed_attempts += 1
        record.updated_at = checked_at
        session.add(record)
        session.commit()
        raise InvalidVerificationCodeError("Invalid verification code")

    record.consumed_at = checked_at
    record.updated_at = checked_at
    session.add(record)


def verify_email_code(
    *, session: Session, user: User, code: str, now: datetime | None = None
) -> None:
    """Confirm a signup code and mark the account verified."""
    check_verification_code(session=session, user=user, code=code, now=now)
    user.is_verified = True
    session.add(user)
    session.commit()
    session.refresh(user)


def mask_email(email: str) -> str:
    local, separator, domain = email.partition("@")
    if not separator:
        return email
    visible = local[:2] if len(local) > 2 else local[:1]
    return f"{visible}{'*' * max(3, len(local) - len(visible))}@{domain}"
