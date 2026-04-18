"""
CSRF (Cross-Site Request Forgery) protection middleware and utilities.

This module provides CSRF protection by:
1. Generating CSRF tokens and sending them to clients
2. Validating CSRF tokens on state-changing requests (POST, PUT, PATCH, DELETE)
3. Excluding safe endpoints (health checks, login, logout)
4. Using double-submit cookie pattern with token in header validation
"""

import logging
import secrets

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

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
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/guest-login",
    "/api/v1/auth/logout",
    "/api/v1/auth/refresh",
}

# HTTP methods that require CSRF protection
CSRF_PROTECTED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


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

    # Tokens must match
    if token_from_cookie != token_from_header:
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
        # Skip CSRF check for exempt paths
        if request.url.path in CSRF_EXEMPT_PATHS:
            return await call_next(request)

        # Skip CSRF check for safe methods (GET, HEAD, OPTIONS)
        if request.method not in CSRF_PROTECTED_METHODS:
            # For safe methods, still provide a new CSRF token
            response = await call_next(request)

            # Add CSRF token to response cookie for safe methods
            # Client will read this and send it back in next non-safe request
            csrf_token = generate_csrf_token()
            self._set_csrf_cookie(response, csrf_token)

            return response

        # For state-changing methods, validate CSRF token
        csrf_valid = await self._validate_csrf(request)

        if not csrf_valid:
            logger.error(f"CSRF validation failed for {request.method} {request.url.path}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF token validation failed",
                headers={
                    "X-CSRF-Error": "invalid_token",
                    "Pragma": "no-cache",
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                },
            )

        # CSRF valid, process request
        response = await call_next(request)

        # Generate new CSRF token for next request
        csrf_token = generate_csrf_token()
        self._set_csrf_cookie(response, csrf_token)

        return response

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
        """
        Set CSRF token cookie in response.

        Args:
            response: The HTTP response
            token: The CSRF token to set
        """
        secure = settings.ENVIRONMENT != "local"

        response.set_cookie(
            key=settings.CSRF_COOKIE_NAME,
            value=token,
            httponly=False,  # Must be readable by JavaScript to send in header
            secure=secure,  # HTTPS only in production
            samesite="lax",  # Prevent cross-site cookie sending
            max_age=60 * 60 * 24,  # 24 hours
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


async def get_csrf_token(request: Request) -> dict:
    """
    Get current CSRF token from request or generate new one.

    This is designed to be used as a route handler.

    Args:
        request: The HTTP request

    Returns:
        Dictionary with CSRF token information
    """
    # Try to get existing token from cookie
    existing_token = request.cookies.get(settings.CSRF_COOKIE_NAME)

    if existing_token:
        return {
            "csrf_token": existing_token,
            "header_name": settings.CSRF_HEADER_NAME,
        }

    # Generate new token if not present
    new_token = generate_csrf_token()
    return {
        "csrf_token": new_token,
        "header_name": settings.CSRF_HEADER_NAME,
    }
