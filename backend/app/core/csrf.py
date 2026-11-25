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
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

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

    # Tokens must match (constant-time, so the comparison leaks nothing)
    if not secrets.compare_digest(token_from_cookie, token_from_header):
        logger.warning("CSRF token mismatch - tokens don't match")
        return False

    # Tokens must be valid format (URL-safe base64, 32 chars min)
    if len(token_from_cookie) < 32:
        logger.warning("CSRF token too short")
        return False

    return True


class CSRFMiddleware(BaseHTTPMiddleware):
    """
    CSRF protection middleware for FastAPI.

    - Generates CSRF tokens for GET requests
    - Validates CSRF tokens for state-changing requests
    - Excludes safe and public endpoints
    - Uses double-submit cookie pattern
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Process request and validate/generate CSRF tokens.

        Args:
            request: The incoming HTTP request
            call_next: The next middleware or route handler

        Returns:
            Response with CSRF token cookie if applicable
        """
        # Exempt auth endpoints skip the token check but still refuse cross-site posts
        if request.url.path in CSRF_EXEMPT_PATHS:
            if (
                request.method in CSRF_PROTECTED_METHODS
                and request.url.path in ORIGIN_CHECKED_PATHS
                and not is_trusted_origin(request)
            ):
                logger.error(f"Cross-site request refused for {request.method} {request.url.path}")
                return self._forbidden("Cross-site request refused", "cross_site_request")
            return await call_next(request)

        # Skip CSRF check for safe methods (GET, HEAD, OPTIONS)
        if request.method not in CSRF_PROTECTED_METHODS:
            response = await call_next(request)
            # Issue a token only when the client has none. Rotating on every
            # response races with parallel requests that already read the old one.
            self._ensure_csrf_cookie(request, response)
            return response

        # For state-changing methods, validate CSRF token
        csrf_valid = await self._validate_csrf(request)

        if not csrf_valid:
            logger.error(f"CSRF validation failed for {request.method} {request.url.path}")
            return self._forbidden("CSRF token validation failed", "invalid_token")

        # CSRF valid, process request. The token stays the same until login/logout.
        return await call_next(request)

    @staticmethod
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

    def _ensure_csrf_cookie(self, request: Request, response: Response) -> None:
        if request.cookies.get(settings.CSRF_COOKIE_NAME):
            return
        cookie_prefix = f"{settings.CSRF_COOKIE_NAME}=".encode()
        if any(
            name == b"set-cookie" and value.startswith(cookie_prefix)
            for name, value in response.raw_headers
        ):
            return
        self._set_csrf_cookie(response, generate_csrf_token())

    async def _validate_csrf(self, request: Request) -> bool:
        """
        Validate CSRF token from request.

        Gets token from:
        1. Cookie (settings.CSRF_COOKIE_NAME)
        2. Header (settings.CSRF_HEADER_NAME)

        Args:
            request: The HTTP request

        Returns:
            True if CSRF token is valid, False otherwise
        """
        # Get CSRF token from cookie
        token_from_cookie = request.cookies.get(settings.CSRF_COOKIE_NAME)

        # Get CSRF token from header
        token_from_header = request.headers.get(settings.CSRF_HEADER_NAME)

        # Validate tokens
        return validate_csrf_token(token_from_cookie, token_from_header)

    def _set_csrf_cookie(self, response: Response, token: str) -> None:
        set_csrf_cookie(response, token)


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
