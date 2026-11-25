"""Session, token and account-lifecycle protections (milestone M1)."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlmodel import Session

from app import crud
from app.core.config import Settings, settings
from app.core.csrf import validate_csrf_token
from app.main import app
from app.models.user import User, UserCreate

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


def test_csrf_tokens_are_compared_exactly() -> None:
    token = "a" * 43

    assert validate_csrf_token(token, token) is True
    assert validate_csrf_token(token, token[:-1] + "b") is False
    assert validate_csrf_token(token, None) is False


def test_staging_requires_a_secret_key() -> None:
    with pytest.raises(ValidationError, match="must be set in staging"):
        Settings(ENVIRONMENT="staging", SECRET_KEY="", POSTGRES_PASSWORD="strong-db-password")
