from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlmodel import Session

from app import crud
from app.main import app
from app.models.user import UserCreate

client = TestClient(app)


def _capture_delivery(monkeypatch) -> tuple[dict[str, str], Callable[..., None]]:
    delivered: dict[str, str] = {}

    def capture(*, recipient: str, code: str, recipient_name: str | None = None) -> None:
        delivered["recipient"] = recipient
        delivered["code"] = code

    monkeypatch.setattr("app.api.routes.user.send_verification_email", capture, raising=False)
    return delivered, capture


def test_signup_requires_email_verification(session: Session, monkeypatch) -> None:
    delivered, _ = _capture_delivery(monkeypatch)

    response = client.post(
        "/api/v1/users/signup",
        json={
            "email": "new-account@example.com",
            "password": "secure-password",
            "full_name": "New Account",
        },
    )

    assert response.status_code == 201
    assert response.json()["masked_email"] == "ne*********@example.com"
    assert delivered["recipient"] == "new-account@example.com"
    user = crud.get_user_by_email(session=session, email="new-account@example.com")
    assert user is not None
    assert user.is_verified is False


def test_verify_email_signs_user_in(session: Session, monkeypatch) -> None:
    delivered, _ = _capture_delivery(monkeypatch)
    client.post(
        "/api/v1/users/signup",
        json={"email": "verified@example.com", "password": "secure-password"},
    )

    response = client.post(
        "/api/v1/users/verify-email",
        json={"email": "verified@example.com", "code": delivered["code"]},
    )

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert "auth-access-token" in response.cookies
    user = crud.get_user_by_email(session=session, email="verified@example.com")
    assert user is not None
    assert user.is_verified is True


def test_login_rejects_unverified_user(session: Session) -> None:
    crud.create_user(
        session=session,
        user_create=UserCreate(email="pending@example.com", password="secure-password"),
        is_verified=False,
    )

    response = client.post(
        "/api/v1/login/access-token",
        data={"username": "pending@example.com", "password": "secure-password"},
    )

    assert response.status_code == 403
    assert response.json()["error"] == "email_not_verified"


def test_resend_is_neutral_for_unknown_email(monkeypatch) -> None:
    _capture_delivery(monkeypatch)

    response = client.post(
        "/api/v1/users/resend-verification",
        json={"email": "missing@example.com"},
    )

    assert response.status_code == 202
    assert response.json()["retry_after_seconds"] == 60


def test_email_change_requires_reverification(session: Session, monkeypatch) -> None:
    delivered, _ = _capture_delivery(monkeypatch)
    user = crud.create_user(
        session=session,
        user_create=UserCreate(email="current@example.com", password="secure-password"),
    )
    user.is_verified = True
    session.add(user)
    session.commit()

    browser = TestClient(app)
    login_response = browser.post(
        "/api/v1/login/access-token",
        data={"username": "current@example.com", "password": "secure-password"},
    )
    assert login_response.status_code == 200
    csrf_token = browser.cookies.get("csrf-token")
    assert csrf_token

    response = browser.post(
        "/api/v1/users/me/email-change",
        json={"new_email": "replacement@example.com", "password": "secure-password"},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 202
    assert delivered["recipient"] == "replacement@example.com"
    session.refresh(user)
    assert user.email == "replacement@example.com"
    assert user.is_verified is False


def test_profile_patch_cannot_bypass_email_verification(session: Session) -> None:
    user = crud.create_user(
        session=session,
        user_create=UserCreate(email="profile@example.com", password="secure-password"),
    )
    browser = TestClient(app)
    login_response = browser.post(
        "/api/v1/login/access-token",
        data={"username": user.email, "password": "secure-password"},
    )
    assert login_response.status_code == 200
    csrf_token = browser.cookies.get("csrf-token")
    assert csrf_token

    response = browser.patch(
        "/api/v1/users/me",
        json={"email": "bypass@example.com"},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 400
    session.refresh(user)
    assert user.email == "profile@example.com"
