"""
CSRF (Cross-Site Request Forgery) protection middleware and utilities.

This module provides CSRF protection by:
1. Generating CSRF tokens and sending them to clients
2. Validating CSRF tokens on state-changing requests (POST, PUT, PATCH, DELETE)
3. Excluding safe endpoints (health checks, login, logout)
4. Using double-submit cookie pattern with token in header validation
5. Checking Origin / Sec-Fetch-Site on the exempt auth endpoints, which set or
   clear session cookies and so must not accept cross-site form posts
"""

import logging
import secrets

from fastapi import Request, status
from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings

logger = logging.getLogger(__name__)

# Endpoints that should be excluded from CSRF protection
# These are typically endpoints that don't modify state or are public
CSRF_EXEMPT_PATHS: set[str] = {
    "/health/live",
    "/health/ready",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/v1/login/access-token",
    "/api/v1/users/signup",
    "/api/v1/users/verify-email",
    "/api/v1/users/resend-verification",
    "/api/v1/auth/logout",
    "/api/v1/auth/refresh",
}

# Exempt endpoints that set or clear auth cookies. A browser has no CSRF token
# before signing in, so these are protected by an Origin check instead.
ORIGIN_CHECKED_PATHS: set[str] = {
    "/api/v1/login/access-token",
    "/api/v1/users/signup",
    "/api/v1/users/verify-email",
    "/api/v1/users/resend-verification",
    "/api/v1/auth/logout",
    "/api/v1/auth/refresh",
}

# HTTP methods that require CSRF protection
CSRF_PROTECTED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def is_trusted_origin(request: Request) -> bool:
    """
    Reject cross-site browser requests.

    Browsers always send Origin on cross-site POSTs, and modern ones send
    Sec-Fetch-Site. Requests carrying neither come from non-browser clients,
    which can't ride on a victim's cookies, so they are allowed.
    """
    origin = request.headers.get("origin")
    if origin is not None:
        own_origin = f"{request.url.scheme}://{request.url.netloc}"
        return origin.rstrip("/") in {own_origin, *settings.all_cors_origins}

    return request.headers.get("sec-fetch-site") != "cross-site"


def generate_csrf_token() -> str:
    """
    Generate a cryptographically secure CSRF token.

    Returns:
        A secure random token string
    """
    return secrets.token_urlsafe(32)


def validate_csrf_token(token_from_cookie: str | None, token_from_header: str | None) -> bool:
    """
    Validate CSRF token using double-submit cookie pattern.

    The token from cookie should match the token from header.
    This prevents CSRF attacks because:
    1. Browsers allow scripts to read cookies, but not set headers from other origins
    2. Cross-origin requests cannot set custom headers (without CORS)
    3. So an attacker cannot forge both a matching cookie and header

    Args:
        token_from_cookie: CSRF token from cookie
        token_from_header: CSRF token from header

    Returns:
        True if tokens are valid and match, False otherwise
    """
    # Both tokens must be present
    if not token_from_cookie or not token_from_header:
        logger.warning("Missing CSRF token - no cookie or header token")
        return False

    # Tokens must match (constant-time, so the comparison leaks nothing). Compare bytes:
    # compare_digest raises TypeError for non-ASCII str, which a client controls
    if not secrets.compare_digest(token_from_cookie.encode(), token_from_header.encode()):
        logger.warning("CSRF token mismatch - tokens don't match")
        return False

    # Tokens must be valid format (URL-safe base64, 32 chars min)
    if len(token_from_cookie) < 32:
        logger.warning("CSRF token too short")
        return False

    return True


class CSRFMiddleware:
    """
    CSRF protection, as pure ASGI middleware.

    - State-changing requests must carry the CSRF cookie's value in the header
      (double-submit cookie pattern)
    - Exempt endpoints skip that, and the ones that set or clear auth cookies
      refuse cross-site browser requests instead
    - Safe requests get a token cookie when the client has none
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        path = scope["path"]
        method = scope["method"]

        if path in CSRF_EXEMPT_PATHS:
            if (
                method in CSRF_PROTECTED_METHODS
                and path in ORIGIN_CHECKED_PATHS
                and not is_trusted_origin(request)
            ):
                logger.error(f"Cross-site request refused for {method} {path}")
                await _forbidden("Cross-site request refused", "cross_site_request")(
                    scope, receive, send
                )
                return
            await self.app(scope, receive, send)
            return

        if method in CSRF_PROTECTED_METHODS:
            token_from_cookie = request.cookies.get(settings.CSRF_COOKIE_NAME)
            token_from_header = request.headers.get(settings.CSRF_HEADER_NAME)
            if not validate_csrf_token(token_from_cookie, token_from_header):
                logger.error(f"CSRF validation failed for {method} {path}")
                await _forbidden("CSRF token validation failed", "invalid_token")(
                    scope, receive, send
                )
                return
            # The token stays the same until login/logout
            await self.app(scope, receive, send)
            return

        if request.cookies.get(settings.CSRF_COOKIE_NAME):
            await self.app(scope, receive, send)
            return

        # Issue a token only when the client has none. Rotating on every response
        # races with parallel requests that already read the old one.
        async def send_with_token(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                cookie_prefix = f"{settings.CSRF_COOKIE_NAME}="
                if not any(
                    value.startswith(cookie_prefix) for value in headers.getlist("set-cookie")
                ):
                    headers.append("set-cookie", _csrf_cookie_header(generate_csrf_token()))
            await send(message)

        await self.app(scope, receive, send_with_token)


def _forbidden(message: str, error_header: str) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={
            "status": "error",
            "error": "authorization_error",
            "message": message,
        },
        headers={
            "X-CSRF-Error": error_header,
            "Pragma": "no-cache",
            "Cache-Control": "no-cache, no-store, must-revalidate",
        },
    )


def _csrf_cookie_header(token: str) -> str:
    """The Set-Cookie value set_csrf_cookie would produce, for a raw ASGI message."""
    carrier = Response()
    set_csrf_cookie(carrier, token)
    return carrier.headers["set-cookie"]


def set_csrf_cookie(response: Response, token: str) -> None:
    """Set the CSRF cookie; it lives as long as the session it protects."""
    response.set_cookie(
        key=settings.CSRF_COOKIE_NAME,
        value=token,
        httponly=False,  # Must be readable by JavaScript to send in header
        secure=settings.ENVIRONMENT != "local",  # HTTPS only in production
        samesite="lax",  # Prevent cross-site cookie sending
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path="/",
    )


class CSRFTokenResponse:
    """Response model for CSRF token endpoints."""

    def __init__(self, token: str):
        self.token = token
        self.header_name = "X-CSRF-Token"
        self.cookie_name = "csrf-token"

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON response."""
        return {
            "csrf_token": self.token,
            "header_name": self.header_name,
        }


async def get_csrf_token(request: Request, response: Response) -> dict:
    """
    Get current CSRF token from request or generate new one.

    This is designed to be used as a route handler. The returned token is always
    the one in the cookie, so the header and cookie match.

    Args:
        request: The HTTP request
        response: The response that carries the cookie

    Returns:
        Dictionary with CSRF token information
    """
    token = request.cookies.get(settings.CSRF_COOKIE_NAME) or generate_csrf_token()
    set_csrf_cookie(response, token)
    return {
        "csrf_token": token,
        "header_name": settings.CSRF_HEADER_NAME,
    }
