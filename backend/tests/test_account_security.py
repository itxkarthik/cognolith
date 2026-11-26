"""Session, token and account-lifecycle protections (milestone M1)."""

import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError
from sqlmodel import Session, col, select

from app import crud
from app.core import security
from app.core.config import Settings, settings
from app.core.csrf import validate_csrf_token
from app.main import app
from app.models.backup import OAuthState
from app.models.document import Document
from app.models.user import EmailVerificationCode, RefreshToken, TokenBlacklist, User, UserCreate
from app.services import auth_service
from app.services.email_service import EmailDeliveryError
from app.services.maintenance_scheduler import cleanup_expired_auth_records

API = settings.API_V1_STR
PASSWORD = "secure-password"


def _create_user(session: Session, email: str = "owner@example.com") -> User:
    return crud.create_user(session=session, user_create=UserCreate(email=email, password=PASSWORD))


def _sign_in(email: str = "owner@example.com") -> tuple[TestClient, str]:
    browser = TestClient(app)
    response = browser.post(
        f"{API}/login/access-token", data={"username": email, "password": PASSWORD}
    )
    assert response.status_code == 200
    csrf_token = browser.cookies.get(settings.CSRF_COOKIE_NAME)
    assert csrf_token
    return browser, csrf_token


def test_login_does_not_return_the_refresh_token_in_the_body(session: Session) -> None:
    _create_user(session)

    browser, _ = _sign_in()
    response = browser.post(
        f"{API}/login/access-token", data={"username": "owner@example.com", "password": PASSWORD}
    )

    assert set(response.json()) == {"access_token", "token_type"}
    assert browser.cookies.get(settings.REFRESH_TOKEN_COOKIE_NAME)


def test_password_change_signs_out_other_sessions_but_keeps_this_one(session: Session) -> None:
    _create_user(session)
    browser, csrf_token = _sign_in()
    other_device, _ = _sign_in()
    stolen_refresh = other_device.cookies.get(settings.REFRESH_TOKEN_COOKIE_NAME)

    response = browser.patch(
        f"{API}/users/me/password",
        json={"current_password": PASSWORD, "new_password": "another-secure-password"},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 200
    assert browser.get(f"{API}/users/me").status_code == 200
    assert other_device.get(f"{API}/users/me").status_code == 401
    relogin = TestClient(app).post(
        f"{API}/login/access-token",
        data={"username": "owner@example.com", "password": "another-secure-password"},
    )
    assert relogin.status_code == 200
    replay = TestClient(app)
    replay.cookies.set(settings.REFRESH_TOKEN_COOKIE_NAME, stolen_refresh or "")
    assert replay.post(f"{API}/auth/refresh").status_code == 401


def test_revoke_all_rejects_access_tokens_immediately(session: Session) -> None:
    _create_user(session)
    browser, csrf_token = _sign_in()
    other_device, _ = _sign_in()

    response = browser.post(f"{API}/auth/revoke-all", headers={"X-CSRF-Token": csrf_token})

    assert response.status_code == 200
    assert other_device.get(f"{API}/users/me").status_code == 401


def test_tokens_from_before_versioning_stop_working_after_sessions_end(session: Session) -> None:
    user = _create_user(session)
    legacy_token = jwt.encode(
        {
            "sub": str(user.id),
            "jti": "legacy",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        settings.SECRET_KEY,
        algorithm=security.ALGORITHM,
    )
    headers = {"Authorization": f"Bearer {legacy_token}"}
    assert TestClient(app).get(f"{API}/users/me", headers=headers).status_code == 200

    auth_service.end_all_sessions(session=session, user=user)

    assert TestClient(app).get(f"{API}/users/me", headers=headers).status_code == 401


def test_revoke_token_also_revokes_the_session_refresh_token(session: Session) -> None:
    _create_user(session)
    browser, csrf_token = _sign_in()
    refresh_token = browser.cookies.get(settings.REFRESH_TOKEN_COOKIE_NAME)
    assert refresh_token

    response = browser.post(f"{API}/auth/revoke-token", headers={"X-CSRF-Token": csrf_token})

    assert response.status_code == 200
    db_token = session.exec(
        select(RefreshToken).where(
            RefreshToken.hashed_token == security.hash_refresh_token(refresh_token)
        )
    ).one()
    assert db_token.revoked is True


@pytest.mark.parametrize(
    "token",
    [
        "not-a-jwt",
        jwt.encode({"sub": "1"}, "wrong-key-" + "x" * 32, algorithm=security.ALGORITHM),
        jwt.encode(
            {"sub": "1", "exp": datetime.now(UTC) - timedelta(minutes=1)},
            settings.SECRET_KEY,
            algorithm=security.ALGORITHM,
        ),
    ],
    ids=["malformed", "bad-signature", "expired"],
)
def test_invalid_access_tokens_get_401_so_clients_refresh(token: str) -> None:
    response = TestClient(app).get(f"{API}/users/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_token_for_a_deleted_user_gets_401(session: Session) -> None:
    token = security.create_access_token(subject=999_999, expires_delta=timedelta(minutes=5))

    response = TestClient(app).get(f"{API}/users/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_account_deletion_requires_the_password(session: Session) -> None:
    _create_user(session)
    browser, csrf_token = _sign_in()

    response = browser.request(
        "DELETE",
        f"{API}/users/me",
        json={"password": "wrong-password"},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 400
    assert crud.get_user_by_email(session=session, email="owner@example.com") is not None


def test_account_deletion_removes_uploaded_files(session: Session, tmp_path: Path) -> None:
    user = _create_user(session)
    upload = tmp_path / "upload.txt"
    upload.write_text("private notes")
    session.add(
        Document(
            user_id=user.id,
            title="Private",
            file_name="upload.txt",
            file_path=str(upload),
            file_size=13,
            file_type=".txt",
            mime_type="text/plain",
            status="completed",
        )
    )
    session.commit()
    browser, csrf_token = _sign_in()

    response = browser.request(
        "DELETE",
        f"{API}/users/me",
        json={"password": PASSWORD},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 200
    assert not upload.exists()
    session.expire_all()
    assert crud.get_user_by_email(session=session, email="owner@example.com") is None


def test_csrf_tokens_are_compared_exactly() -> None:
    token = "a" * 43

    assert validate_csrf_token(token, token) is True
    assert validate_csrf_token(token, token[:-1] + "b") is False
    assert validate_csrf_token(token, None) is False
    # Non-ASCII input is a client error, not a crash
    assert validate_csrf_token(token, "é" * 43) is False


def test_staging_requires_a_secret_key() -> None:
    with pytest.raises(ValidationError, match="must be set in staging"):
        Settings(ENVIRONMENT="staging", SECRET_KEY="", POSTGRES_PASSWORD="strong-db-password")


def test_cleanup_removes_only_expired_auth_records(session: Session) -> None:
    user = _create_user(session)
    assert user.id is not None
    now = datetime.now(UTC)
    old = now - timedelta(days=2)
    session.add_all(
        [
            RefreshToken(user_id=user.id, hashed_token="expired", expires_at=old),
            RefreshToken(
                user_id=user.id, hashed_token="active", expires_at=now + timedelta(days=1)
            ),
            TokenBlacklist(jti="expired-jti", expires_at=old),
            OAuthState(user_id=user.id, state_hash="expired-state", expires_at=old),
            EmailVerificationCode(
                user_id=user.id,
                code_hash="hash",
                expires_at=old,
                resend_available_at=old,
                window_started_at=old,
            ),
        ]
    )
    session.commit()

    removed = cleanup_expired_auth_records(session, now=now)

    assert removed == 4
    remaining = session.exec(select(RefreshToken.hashed_token)).all()
    assert remaining == ["active"]


def test_session_version_bump_is_atomic_even_from_a_stale_copy(session: Session) -> None:
    user = _create_user(session)
    user_id = user.id
    with Session(session.get_bind()) as other:
        stale = other.get(User, user_id)
        assert stale is not None
        auth_service.end_all_sessions(session=session, user=user)
        # `stale` still says version 0; a read-modify-write would write 1 again
        auth_service.end_all_sessions(session=other, user=stale)

    session.refresh(user)
    assert user.token_version == 2


def test_revoke_token_ignores_another_users_refresh_cookie(session: Session) -> None:
    _create_user(session)
    victim = _create_user(session, email="victim@example.com")
    victim_pair = auth_service.create_token_pair(session=session, user=victim)
    browser, csrf_token = _sign_in()
    browser.cookies.set(settings.REFRESH_TOKEN_COOKIE_NAME, victim_pair.refresh_token)

    browser.post(f"{API}/auth/revoke-token", headers={"X-CSRF-Token": csrf_token})

    victim_token = session.exec(
        select(RefreshToken).where(
            RefreshToken.hashed_token == security.hash_refresh_token(victim_pair.refresh_token)
        )
    ).one()
    assert victim_token.revoked is False


def test_stale_session_after_sign_out_everywhere_is_not_reported_as_theft(
    session: Session, caplog: pytest.LogCaptureFixture
) -> None:
    user = _create_user(session)
    pair = auth_service.create_token_pair(session=session, user=user)
    auth_service.end_all_sessions(session=session, user=user)
    for token in session.exec(select(RefreshToken)).all():
        # Past the concurrent-refresh grace window
        token.revoked_at = datetime.now(UTC) - timedelta(minutes=5)
        session.add(token)
    session.commit()

    with pytest.raises(ValueError):
        auth_service.refresh_access_token_from_refresh(
            session=session, refresh_token=pair.refresh_token
        )

    assert "reuse" not in caplog.text


def test_email_change_rejects_the_current_address(session: Session) -> None:
    _create_user(session)
    browser, csrf_token = _sign_in()

    response = browser.post(
        f"{API}/users/me/email-change",
        json={"new_email": "Owner@Example.com", "password": PASSWORD},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 400


def test_pending_email_change_survives_a_reload_and_can_be_cancelled(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.api.routes.user.send_email_change_code", lambda **_: None)
    _create_user(session)
    browser, csrf_token = _sign_in()
    headers = {"X-CSRF-Token": csrf_token}

    browser.post(
        f"{API}/users/me/email-change",
        json={"new_email": "new@example.com", "password": PASSWORD},
        headers=headers,
    )
    assert browser.get(f"{API}/users/me").json()["pending_email"] == "new@example.com"

    cancelled = browser.delete(f"{API}/users/me/email-change", headers=headers)

    assert cancelled.status_code == 200
    assert cancelled.json()["pending_email"] is None
    assert cancelled.json()["email"] == "owner@example.com"
    confirm = browser.post(
        f"{API}/users/me/email-change/confirm", json={"code": "123456"}, headers=headers
    )
    assert confirm.status_code == 400


def test_pending_email_is_not_shown_in_admin_user_listings(session: Session) -> None:
    user = _create_user(session)
    user.pending_email = "new@example.com"
    session.add(user)
    session.commit()
    admin = crud.create_user(
        session=session,
        user_create=UserCreate(email="admin@example.com", password=PASSWORD, is_superuser=True),
    )
    assert admin.id is not None
    browser, _ = _sign_in("admin@example.com")

    listing = browser.get(f"{API}/users/").json()["data"]

    assert all("pending_email" not in row for row in listing)


def test_failed_code_delivery_leaves_no_pending_email_change(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(**_: object) -> None:
        raise EmailDeliveryError("SMTP down")

    monkeypatch.setattr("app.api.routes.user.send_email_change_code", fail)
    _create_user(session)
    browser, csrf_token = _sign_in()

    response = browser.post(
        f"{API}/users/me/email-change",
        json={"new_email": "new@example.com", "password": PASSWORD},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code >= 500
    assert browser.get(f"{API}/users/me").json()["pending_email"] is None


def test_resend_sends_a_fresh_code_to_the_pending_address(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "app.api.routes.user.send_email_change_code",
        lambda *, recipient, code, **_: sent.append((recipient, code)),
    )
    _create_user(session)
    browser, csrf_token = _sign_in()
    headers = {"X-CSRF-Token": csrf_token}
    browser.post(
        f"{API}/users/me/email-change",
        json={"new_email": "new@example.com", "password": PASSWORD},
        headers=headers,
    )

    too_soon = browser.post(f"{API}/users/me/email-change/resend", headers=headers)
    assert too_soon.status_code == 429

    record = session.exec(select(EmailVerificationCode)).one()
    record.resend_available_at = datetime.now(UTC) - timedelta(seconds=1)
    session.add(record)
    session.commit()
    resent = browser.post(f"{API}/users/me/email-change/resend", headers=headers)

    assert resent.status_code == 200
    assert [recipient for recipient, _ in sent] == ["new@example.com", "new@example.com"]
    first_code, latest_code = sent[0][1], sent[1][1]
    if first_code != latest_code:
        stale = browser.post(
            f"{API}/users/me/email-change/confirm", json={"code": first_code}, headers=headers
        )
        assert stale.status_code == 400
    confirmed = browser.post(
        f"{API}/users/me/email-change/confirm", json={"code": latest_code}, headers=headers
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["email"] == "new@example.com"


def test_resend_without_a_pending_change_is_rejected(session: Session) -> None:
    _create_user(session)
    browser, csrf_token = _sign_in()

    response = browser.post(
        f"{API}/users/me/email-change/resend", headers={"X-CSRF-Token": csrf_token}
    )

    assert response.status_code == 400


def test_refresh_in_flight_cannot_outlive_sign_out_everywhere(session: Session) -> None:
    user = _create_user(session)
    assert user.id is not None
    pair = auth_service.create_token_pair(session=session, user=user)
    outcome: dict[str, bool] = {}

    def refresh() -> None:
        with Session(session.get_bind()) as other:
            try:
                auth_service.refresh_access_token_from_refresh(
                    session=other, refresh_token=pair.refresh_token
                )
                outcome["refreshed"] = True
            except ValueError:
                outcome["refreshed"] = False

    with Session(session.get_bind()) as signing_out:
        locked = crud.lock_user(session=signing_out, user_id=user.id)
        assert locked is not None
        worker = threading.Thread(target=refresh)
        worker.start()
        worker.join(timeout=1)
        # The refresh waits for the user lock instead of rotating underneath us
        assert worker.is_alive()
        auth_service.end_all_sessions(session=signing_out, user=locked)
    worker.join(timeout=10)

    assert outcome == {"refreshed": False}
    live = session.exec(
        select(RefreshToken).where(
            RefreshToken.user_id == user.id, col(RefreshToken.revoked).is_(False)
        )
    ).all()
    assert live == []


def test_email_change_code_only_confirms_the_address_it_was_sent_to(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[str] = []
    monkeypatch.setattr(
        "app.api.routes.user.send_email_change_code",
        lambda *, code, **_: sent.append(code),
    )
    user = _create_user(session)
    browser, csrf_token = _sign_in()
    headers = {"X-CSRF-Token": csrf_token}
    browser.post(
        f"{API}/users/me/email-change",
        json={"new_email": "mine@example.com", "password": PASSWORD},
        headers=headers,
    )
    # A racing request leaves a different address pending under the same code
    user.pending_email = "someone-else@example.com"
    session.add(user)
    session.commit()

    response = browser.post(
        f"{API}/users/me/email-change/confirm", json={"code": sent[0]}, headers=headers
    )

    assert response.status_code == 400
    session.refresh(user)
    assert user.email == "owner@example.com"


def test_cleanup_continues_after_one_table_fails(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(_: Session) -> int:
        raise OperationalError("DELETE", {}, Exception("lock timeout"))

    monkeypatch.setattr("app.services.maintenance_scheduler.cleanup_expired_tokens", fail)
    user = _create_user(session)
    assert user.id is not None
    session.add(
        OAuthState(
            user_id=user.id,
            state_hash="expired-state",
            expires_at=datetime.now(UTC) - timedelta(days=1),
        )
    )
    session.commit()

    removed = cleanup_expired_auth_records(session)

    assert removed == 1
    assert session.exec(select(OAuthState)).all() == []
