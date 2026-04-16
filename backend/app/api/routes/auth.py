from datetime import datetime, timedelta, timezone
import secrets
from typing import Annotated, Any

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from app.core import security
from app.core.config import settings
from app.core.csrf import get_csrf_token
from app import crud
from app.api.deps import CurrentUser, SessionDep, TokenDep
from app.models.user import Message, Token, UserPublic, TokenPayload
from app.core.rate_limit import limiter
from app.schemas.error import StandardErrorResponse

router = APIRouter(tags=["login"])


@router.get(
	path="/csrf-token",
	responses={
		200: {"description": "CSRF token successfully generated"},
		500: {"model": StandardErrorResponse, "description": "Internal server error"},
	},
)
async def get_csrf_token_endpoint(request: Request) -> dict:
	"""
	Get a CSRF token for use in subsequent state-changing requests.
	
	This endpoint provides a CSRF token that must be included in the X-CSRF-Token
	header for POST, PUT, PATCH, and DELETE requests.
	
	The token is set in a cookie and must also be sent back in the header for validation.
	"""
	return await get_csrf_token(request)


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
	secure = settings.ENVIRONMENT != "local"
	csrf_token = secrets.token_urlsafe(32)

	response.set_cookie(
		key=settings.ACCESS_TOKEN_COOKIE_NAME,
		value=access_token,
		httponly=True,
		secure=secure,
		samesite="lax",
		max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
		path="/",
	)
	response.set_cookie(
		key=settings.REFRESH_TOKEN_COOKIE_NAME,
		value=refresh_token,
		httponly=True,
		secure=secure,
		samesite="lax",
		max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
		path="/",
	)
	response.set_cookie(
		key=settings.CSRF_COOKIE_NAME,
		value=csrf_token,
		httponly=False,
		secure=secure,
		samesite="lax",
		max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
		path="/",
	)



def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(key=settings.ACCESS_TOKEN_COOKIE_NAME, path="/")
    response.delete_cookie(key=settings.REFRESH_TOKEN_COOKIE_NAME, path="/")
    response.delete_cookie(key=settings.CSRF_COOKIE_NAME, path="/")


@router.post(
	path="/login/access-token",
	responses={
		400: {"model": StandardErrorResponse, "description": "Invalid credentials or inactive user"},
		429: {"model": StandardErrorResponse, "description": "Too many login attempts"},
		500: {"model": StandardErrorResponse, "description": "Internal server error"},
	},
)
@limiter.limit("5/minute")
def login_access_token(
	    request: Request,
	    response: Response,
	    session: SessionDep,
	    form_data: Annotated[OAuth2PasswordRequestForm, Depends()]
	) -> Token:
    """
        OAuth2 token login, get an access token for future requests.
        Rate limited to 5 attempts per minute per IP.
    """
    user = crud.authenticate(
        session=session, email=form_data.username, password=form_data.password
    )
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect Email or Password")
    elif not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        subject=user.id, expires_delta=access_token_expires
    )

    # Issue refresh token
    raw_refresh_token = security.generate_refresh_token()
    crud.create_refresh_token(
        session=session,
        user_id=user.id,
        raw_token=raw_refresh_token,
        expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    _set_auth_cookies(response, access_token=access_token, refresh_token=raw_refresh_token)

    return Token(
        access_token=access_token,
        refresh_token=raw_refresh_token,
    )


class RefreshRequest(BaseModel):
    refresh_token: str | None = None


@router.post(
	path="/auth/refresh",
	responses={
		400: {"model": StandardErrorResponse, "description": "Invalid token format"},
		401: {"model": StandardErrorResponse, "description": "Invalid or expired refresh token"},
		500: {"model": StandardErrorResponse, "description": "Internal server error"},
	},
)
def refresh_access_token(
    request: Request,
    response: Response,
    body: RefreshRequest,
    session: SessionDep,
) -> Token:
    """
    Exchange a valid refresh token for a new access + refresh token pair.
    The old refresh token is revoked (rotation).
    """
    refresh_token = body.refresh_token or request.cookies.get(settings.REFRESH_TOKEN_COOKIE_NAME)
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Missing refresh token")

    hashed = security.hash_refresh_token(refresh_token)
    db_token = crud.get_refresh_token_by_hash(session=session, hashed_token=hashed)

    if not db_token:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    # Revoke old refresh token (single-use rotation)
    crud.revoke_refresh_token(session=session, db_token=db_token)

    # Issue new tokens
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        subject=db_token.user_id, expires_delta=access_token_expires
    )

    raw_refresh_token = security.generate_refresh_token()
    crud.create_refresh_token(
        session=session,
        user_id=db_token.user_id,
        raw_token=raw_refresh_token,
        expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    _set_auth_cookies(response, access_token=access_token, refresh_token=raw_refresh_token)

    return Token(
        access_token=access_token,
        refresh_token=raw_refresh_token,
    )


@router.post(
	path="/auth/logout",
	response_model=Message,
	responses={
		400: {"model": StandardErrorResponse, "description": "Invalid token"},
		401: {"model": StandardErrorResponse, "description": "Authentication required"},
		500: {"model": StandardErrorResponse, "description": "Internal server error"},
	},
)
def logout(response: Response, session: SessionDep, token: TokenDep, current_user: CurrentUser) -> Message:
    """
    Logout: blacklist the current access token and revoke all refresh tokens
    for the user.
    """
    # Decode the current access token to get jti + expiry
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid token")

    # Blacklist the access token so it can't be reused
    if token_data.jti:
        expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        crud.blacklist_token(session=session, jti=token_data.jti, expires_at=expires_at)

    # Revoke all refresh tokens for this user
    crud.revoke_all_user_refresh_tokens(session=session, user_id=current_user.id)
    _clear_auth_cookies(response)

    return Message(message="Successfully logged out")


@router.post(
	path="/login/test-token",
	response_model=UserPublic,
	responses={
		401: {"model": StandardErrorResponse, "description": "Authentication required"},
		500: {"model": StandardErrorResponse, "description": "Internal server error"},
	},
)
def test_token(current_user: CurrentUser) -> Any:
    return current_user
