import secrets
from collections.abc import Generator
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pydantic import ValidationError
from sqlmodel import Session, select

from app.core import security
from app.core.config import settings
from app.core.database import engine
from app.models.user import TokenBlacklist, TokenPayload, User

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/login/access-token",
    auto_error=False,
)


def get_db() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_db)]


def get_auth_token(
    request: Request, bearer_token: Annotated[str | None, Depends(reusable_oauth2)]
) -> str:
    if bearer_token:
        request.state.auth_via_cookie = False
        return bearer_token

    cookie_token = request.cookies.get(settings.ACCESS_TOKEN_COOKIE_NAME)
    if cookie_token:
        request.state.auth_via_cookie = True
        return cookie_token

    request.state.auth_via_cookie = False

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
    )


TokenDep = Annotated[str, Depends(get_auth_token)]


def _validate_csrf(request: Request) -> None:
    cookie_token = request.cookies.get(settings.CSRF_COOKIE_NAME)
    header_token = request.headers.get(settings.CSRF_HEADER_NAME)

    if not cookie_token or not header_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing CSRF token",
        )

    if not secrets.compare_digest(cookie_token, header_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid CSRF token",
        )


UNSAFE_HTTP_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def get_current_user(request: Request, session: SessionDep, token: TokenDep) -> User:
    if getattr(request.state, "auth_via_cookie", False) and request.method in UNSAFE_HTTP_METHODS:
        _validate_csrf(request)

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[security.ALGORITHM])
        token_data = TokenPayload(**payload)
    except (InvalidTokenError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Could not validate credentials"
        )
    # Check if the token has been blacklisted (logout / revocation)
    if token_data.jti:
        blacklisted = session.exec(
            select(TokenBlacklist).where(TokenBlacklist.jti == token_data.jti)
        ).first()
        if blacklisted:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has been revoked"
            )
    user = session.get(User, token_data.sub)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive User")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_current_active_superuser(current_user: CurrentUser) -> User:
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="The user doesn't have enough privileges")
    return current_user
