from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import Session

from app import crud
from app.models.user import EmailVerificationCode, UserCreate
from app.services.email_verification_service import (
    InvalidVerificationCodeError,
    VerificationCodeExpiredError,
    VerificationRateLimitError,
    issue_verification_code,
    verify_email_code,
)


@pytest.fixture
def unverified_user(session: Session):
    return crud.create_user(
        session=session,
        user_create=UserCreate(
            email="verify@example.com",
            password="secure-password",
            full_name="Verify User",
        ),
        is_verified=False,
    )


def test_programmatic_users_are_verified_by_default(session: Session) -> None:
    user = crud.create_user(
        session=session,
        user_create=UserCreate(
            email="managed@example.com",
            password="secure-password",
        ),
    )

    assert user.is_verified is True


def test_issue_stores_only_hash(session: Session, unverified_user) -> None:
    now = datetime.now(UTC)
    issued = issue_verification_code(session=session, user=unverified_user, now=now)

    record = session.get(EmailVerificationCode, unverified_user.id)
    assert issued.code.isdigit()
    assert len(issued.code) == 6
    assert record is not None
    assert record.code_hash != issued.code
    assert record.expires_at == now + timedelta(minutes=10)


def test_wrong_code_locks_after_five_attempts(session: Session, unverified_user) -> None:
    now = datetime.now(UTC)
    issued = issue_verification_code(session=session, user=unverified_user, now=now)
    wrong_code = "000000" if issued.code != "000000" else "000001"

    for _ in range(5):
        with pytest.raises(InvalidVerificationCodeError):
            verify_email_code(
                session=session,
                user=unverified_user,
                code=wrong_code,
                now=now,
            )

    with pytest.raises(InvalidVerificationCodeError):
        verify_email_code(
            session=session,
            user=unverified_user,
            code=wrong_code,
            now=now,
        )


def test_expired_code_is_rejected(session: Session, unverified_user) -> None:
    now = datetime.now(UTC)
    issued = issue_verification_code(session=session, user=unverified_user, now=now)

    with pytest.raises(VerificationCodeExpiredError):
        verify_email_code(
            session=session,
            user=unverified_user,
            code=issued.code,
            now=now + timedelta(minutes=11),
        )


def test_resend_invalidates_previous_code(session: Session, unverified_user) -> None:
    now = datetime.now(UTC)
    first = issue_verification_code(session=session, user=unverified_user, now=now)
    second = issue_verification_code(
        session=session,
        user=unverified_user,
        now=now + timedelta(seconds=61),
    )

    with pytest.raises(InvalidVerificationCodeError):
        verify_email_code(
            session=session,
            user=unverified_user,
            code=first.code,
            now=now + timedelta(seconds=61),
        )

    verify_email_code(
        session=session,
        user=unverified_user,
        code=second.code,
        now=now + timedelta(seconds=61),
    )
    assert unverified_user.is_verified is True


def test_resend_cooldown_and_hourly_limit(session: Session, unverified_user) -> None:
    now = datetime.now(UTC)
    issue_verification_code(session=session, user=unverified_user, now=now)

    with pytest.raises(VerificationRateLimitError):
        issue_verification_code(
            session=session,
            user=unverified_user,
            now=now + timedelta(seconds=30),
        )

    for minute in range(1, 5):
        issue_verification_code(
            session=session,
            user=unverified_user,
            now=now + timedelta(minutes=minute),
        )

    with pytest.raises(VerificationRateLimitError):
        issue_verification_code(
            session=session,
            user=unverified_user,
            now=now + timedelta(minutes=5),
        )
