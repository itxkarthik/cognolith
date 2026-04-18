import secrets
from datetime import UTC, datetime
from typing import Annotated, Any

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from app import crud  # type: ignore[attr-defined]
from app.api.deps import CurrentUser, SessionDep, TokenDep
from app.core import security
from app.core.config import settings
from app.core.csrf import get_csrf_token
from app.core.rate_limit import limiter
from app.models.user import Message, Token, TokenPayload, UserPublic
from app.schemas.error import StandardErrorResponse
from app.services import auth_service

router = APIRouter(tags=["login"])


@router.get(
    path="/csrf-token",
    responses={
        200: {"description": "CSRF token successfully generated"},
        500: {"model": StandardErrorResponse, "description": "Internal server error"},
    },
)
async def get_csrf_token_endpoint(request: Request[Any]) -> dict[str, Any]:
    """
    Get a CSRF token for use in subsequent state-changing requests.

    This endpoint provides a CSRF token that must be included in the X-CSRF-Token
    header for POST, PUT, PATCH, and DELETE requests.

    The token is set in a cookie and must also be sent back in the header for validation.
    """
    return await get_csrf_token(request)  # type: ignore[no-any-return]


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
        400: {
            "model": StandardErrorResponse,
            "description": "Invalid credentials or inactive user",
        },
        429: {"model": StandardErrorResponse, "description": "Too many login attempts"},
        500: {"model": StandardErrorResponse, "description": "Internal server error"},
    },
)
@limiter.limit("5/minute")  # type: ignore[misc]
def login_access_token(
    request: Request[Any],
    response: Response,
    session: SessionDep,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> Token:
    """
    OAuth2 token login, get an access token for future requests.
    Rate limited to 5 attempts per minute per IP.
    """
    user = crud.authenticate(session=session, email=form_data.username, password=form_data.password)
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect Email or Password")
    elif not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")

    # Use auth_service to create token pair
    token_pair = auth_service.create_token_pair(session=session, user=user)
    _set_auth_cookies(
        response, access_token=token_pair.access_token, refresh_token=token_pair.refresh_token
    )

    return Token(
        access_token=token_pair.access_token,
        refresh_token=token_pair.refresh_token,
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
    request: Request[Any],
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

    # Get user from token or request context
    user_id = None
    try:
        # Try to get user_id from current token if available
        token = request.cookies.get(settings.ACCESS_TOKEN_COOKIE_NAME)
        if token:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[security.ALGORITHM])
            user_id = payload.get("sub")
    except Exception:
        pass

    # Use auth_service to refresh with token rotation
    try:
        if user_id:
            token_pair = auth_service.refresh_access_token_from_refresh(
                session=session, user_id=int(user_id), refresh_token=refresh_token
            )
        else:
            # Lookup user by refresh token without knowing user_id first
            hashed = security.hash_refresh_token(refresh_token)
            db_token = crud.get_refresh_token_by_hash(session=session, hashed_token=hashed)
            if not db_token:
                raise ValueError("Invalid or expired refresh token")
            token_pair = auth_service.refresh_access_token_from_refresh(
                session=session, user_id=db_token.user_id, refresh_token=refresh_token
            )
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid refresh token")

    _set_auth_cookies(
        response, access_token=token_pair.access_token, refresh_token=token_pair.refresh_token
    )

    return Token(
        access_token=token_pair.access_token,
        refresh_token=token_pair.refresh_token,
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
def logout(
    response: Response, session: SessionDep, token: TokenDep, current_user: CurrentUser
) -> Message:
    """
    Logout: blacklist the current access token and revoke all refresh tokens
    for the user.
    """
    # Decode the current access token to get jti + expiry
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[security.ALGORITHM])
        token_data = TokenPayload(**payload)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid token")

    # Use auth_service to revoke tokens
    if token_data.jti:
        expires_at = datetime.fromtimestamp(payload["exp"], tz=UTC)
        auth_service.revoke_access_token(session=session, jti=token_data.jti, expires_at=expires_at)

    # Revoke all refresh tokens for this user
    auth_service.revoke_all_user_tokens(session=session, user_id=current_user.id)
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


class RevokeTokenRequest(BaseModel):
    """Request model for explicit token revocation."""

    reason: str | None = None  # Optional reason for audit logging


class TokenInfoResponse(BaseModel):
    """Response model for token information."""

    user_id: int
    jti: str | None
    expires_at: datetime | None
    is_blacklisted: bool | None
    is_expired: bool | None
    issued_at: datetime | None


@router.post(
    path="/auth/revoke-token",
    response_model=Message,
    responses={
        400: {"model": StandardErrorResponse, "description": "Invalid token"},
        401: {"model": StandardErrorResponse, "description": "Authentication required"},
        500: {"model": StandardErrorResponse, "description": "Internal server error"},
    },
)
def revoke_current_token(
    response: Response,
    session: SessionDep,
    token: TokenDep,
    current_user: CurrentUser,
    body: RevokeTokenRequest = RevokeTokenRequest(),
) -> Message:
    """
    Explicitly revoke the current access token.

    Used for security-conscious logout or when revoking a specific token
    while keeping other sessions active.

    Args:
            body: Optional reason for audit logging (not stored, just for audit trail)

    Returns:
            Success message
    """
    # Decode token to get jti + expiry
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[security.ALGORITHM])
        token_data = TokenPayload(**payload)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid token")

    # Revoke the access token
    if token_data.jti:
        expires_at = datetime.fromtimestamp(payload["exp"], tz=UTC)
        auth_service.revoke_access_token(session=session, jti=token_data.jti, expires_at=expires_at)

    # Clear auth cookies
    _clear_auth_cookies(response)

    return Message(message="Token revoked successfully")


@router.post(
    path="/auth/revoke-all",
    response_model=Message,
    responses={
        401: {"model": StandardErrorResponse, "description": "Authentication required"},
        500: {"model": StandardErrorResponse, "description": "Internal server error"},
    },
)
def revoke_all_user_tokens_endpoint(
    response: Response, session: SessionDep, current_user: CurrentUser
) -> Message:
    """
    Revoke ALL tokens for the current user (logout from all devices).

    Used for:
    - Security incident response
    - Account password change
    - User explicitly requesting logout everywhere

    All existing sessions become invalid immediately.
    User must login again.

    Returns:
            Success message
    """
    # Revoke all tokens
    auth_service.revoke_all_user_tokens(session=session, user_id=current_user.id)
    _clear_auth_cookies(response)

    return Message(message="All tokens revoked successfully")


@router.get(
    path="/auth/token-info",
    response_model=TokenInfoResponse,
    responses={
        400: {"model": StandardErrorResponse, "description": "Invalid token"},
        401: {"model": StandardErrorResponse, "description": "Authentication required"},
        500: {"model": StandardErrorResponse, "description": "Internal server error"},
    },
)
def get_token_info_endpoint(
    session: SessionDep, token: TokenDep, current_user: CurrentUser
) -> TokenInfoResponse:
    """
    Get information about the current access token.

    Useful for debugging token lifecycle and checking token status.

    Returns:
            TokenInfoResponse with:
            - user_id: User ID from token
            - jti: JWT ID for revocation tracking
            - expires_at: Token expiration timestamp
            - is_blacklisted: Whether token has been revoked
            - is_expired: Whether token has expired
            - issued_at: Token issue timestamp
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[security.ALGORITHM])
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid token")

    # Get token info
    token_info = auth_service.get_token_info(session=session, token_payload=payload)

    return TokenInfoResponse(
        user_id=token_info["user_id"],
        jti=token_info["jti"],
        expires_at=token_info["expires_at"],
        is_blacklisted=token_info["is_blacklisted"],
        is_expired=token_info["is_expired"],
        issued_at=datetime.fromtimestamp(payload.get("iat", 0), tz=UTC)
        if payload.get("iat")
        else None,
    )
