"""Session, token and account-lifecycle protections (milestone M1)."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlmodel import Session

from app import crud
from app.core import security
from app.core.config import Settings, settings
from app.core.csrf import validate_csrf_token
from app.main import app
from app.models.user import User, UserCreate
from app.services import auth_service

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


def test_csrf_tokens_are_compared_exactly() -> None:
    token = "a" * 43

    assert validate_csrf_token(token, token) is True
    assert validate_csrf_token(token, token[:-1] + "b") is False
    assert validate_csrf_token(token, None) is False


def test_staging_requires_a_secret_key() -> None:
    with pytest.raises(ValidationError, match="must be set in staging"):
        Settings(ENVIRONMENT="staging", SECRET_KEY="", POSTGRES_PASSWORD="strong-db-password")


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
