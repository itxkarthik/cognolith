"""
HTTP middleware, all pure ASGI.

Each one edits the `http.response.start` message as it passes, so no response body
is wrapped or buffered (the ETag middleware buffers only what it fingerprints).
BaseHTTPMiddleware ran every layer in its own task with a memory stream, adding
latency per request and getting in the way of streamed responses.
"""

import json
import logging
import re
import time
import uuid

from slowapi import Limiter
from slowapi.middleware import _find_route_handler, _should_exempt, async_check_limits
from starlette.applications import Starlette
from starlette.datastructures import Headers, MutableHeaders
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings

logger = logging.getLogger(__name__)

DEFAULT_CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "frame-ancestors 'none'"
)

DOCS_CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
    "img-src 'self' data: https://fastapi.tiangolo.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "connect-src 'self'; "
    "frame-ancestors 'none'"
)

DOCS_PATHS = {"/docs", "/docs/oauth2-redirect", "/redoc"}


def content_security_policy_for_path(path: str) -> str:
    if path in DOCS_PATHS:
        return DOCS_CONTENT_SECURITY_POLICY
    return DEFAULT_CONTENT_SECURITY_POLICY


class SecurityHeadersMiddleware:
    """Add the security headers to every HTTP response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        policy = content_security_policy_for_path(scope["path"])

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                # Prevent MIME-type sniffing
                headers["X-Content-Type-Options"] = "nosniff"
                # Prevent clickjacking: deny all iframe embedding
                headers["X-Frame-Options"] = "DENY"
                headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
                headers["Permissions-Policy"] = (
                    "camera=(), microphone=(), geolocation=(), browsing-topics=()"
                )
                # Documentation uses FastAPI's pinned CDN assets; other routes stay same-origin
                headers["Content-Security-Policy"] = policy
                # HSTS only in staging/production (not local dev)
                if settings.ENVIRONMENT != "local":
                    headers["Strict-Transport-Security"] = (
                        "max-age=63072000; includeSubDomains; preload"
                    )
            await send(message)

        await self.app(scope, receive, send_with_headers)


# Client-supplied ids are echoed into logs and headers, so only plain tokens are kept
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


class RequestIDMiddleware:
    """
    Give every request an id, reused from `X-Request-ID` when it is a plain token.

    The id is stored on `request.state.request_id` for logs and error responses and
    returned in the `X-Request-ID` response header.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        supplied = Headers(scope=scope).get("x-request-id")
        request_id = (
            supplied if supplied and _REQUEST_ID_PATTERN.fullmatch(supplied) else str(uuid.uuid4())
        )
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
            await send(message)

        await self.app(scope, receive, send_with_id)


def _body_too_large_detail() -> str:
    return f"Request body too large. Maximum: {settings.MAX_REQUEST_BODY_SIZE // (1024 * 1024)} MB"


class RequestBodyTooLarge(HTTPException):
    """
    Raised from the wrapped ASGI receive channel once the body exceeds the limit.

    Subclassing HTTPException keeps FastAPI's body parser from turning it into a 400.
    """

    def __init__(self) -> None:
        super().__init__(status_code=413, detail=_body_too_large_detail())


def _body_too_large_response() -> JSONResponse:
    return JSONResponse(status_code=413, content={"detail": _body_too_large_detail()})


class MaxRequestBodySizeMiddleware:
    """
    Rejects requests whose body exceeds the configured limit.

    The declared Content-Length is checked up front, and the streamed body is
    counted as it is received so chunked requests without a Content-Length are
    capped as well.
    """

    def __init__(self, app: ASGIApp, max_body_size: int | None = None) -> None:
        self.app = app
        self.max_body_size = max_body_size or settings.MAX_REQUEST_BODY_SIZE

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        content_length = headers.get("content-length")
        if content_length is not None:
            try:
                declared_size = int(content_length)
            except ValueError:
                declared_size = -1
            if declared_size < 0:
                response = JSONResponse(
                    status_code=400, content={"detail": "Invalid Content-Length header"}
                )
                await response(scope, receive, send)
                return
            if declared_size > self.max_body_size:
                await _body_too_large_response()(scope, receive, send)
                return

        received = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_size:
                    raise RequestBodyTooLarge
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except RequestBodyTooLarge:
            if not response_started:
                await _body_too_large_response()(scope, receive, send)


class RequestLoggingMiddleware:
    """
    Log each request and its response as structured JSON.

    Runs inside RequestIDMiddleware, so every line carries the request id. The
    elapsed time covers the whole response, the full duration of a stream included.
    Health checks are logged only when they fail.
    """

    MINIMAL_LOG_PATHS = {"/health", "/health/live", "/health/ready"}

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        request_id = scope.get("state", {}).get("request_id", "unknown")
        path = scope["path"]
        query = scope.get("query_string", b"").decode("latin-1") or None
        client = scope.get("client")
        base = {
            "request_id": request_id,
            "method": scope["method"],
            "path": path,
            "query": query,
        }
        is_minimal_path = path in self.MINIMAL_LOG_PATHS
        if not is_minimal_path:
            logger.debug(
                json.dumps(
                    {
                        "event": "request",
                        **base,
                        "client": client[0] if client else None,
                        "user_agent": Headers(scope=scope).get("user-agent"),
                    }
                )
            )
        status_code: int | None = None

        async def send_and_record(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_and_record)
        except Exception as exc:
            logger.error(
                json.dumps(
                    {
                        "event": "request_error",
                        **base,
                        "client": client[0] if client else None,
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                        "elapsed_ms": _elapsed_ms(started),
                    }
                )
            )
            raise
        if status_code is None:
            return  # the client went away before a response started
        response_log = json.dumps(
            {
                "event": "response",
                **base,
                "status": status_code,
                "elapsed_ms": _elapsed_ms(started),
            }
        )
        if status_code >= 500:
            logger.error(response_log)
        elif status_code >= 400:
            logger.warning(response_log)
        elif not is_minimal_path:
            logger.info(response_log)


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 2)


class RateLimitMiddleware:
    """
    Apply the limiter's default limit to routes without their own limit decorator.

    Replaces slowapi's middlewares: SlowAPIMiddleware is a BaseHTTPMiddleware, and
    SlowAPIASGIMiddleware sends `http.response.start` again before every body chunk,
    which breaks any streamed response.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        app: Starlette = scope["app"]
        limiter: Limiter = app.state.limiter
        if not limiter.enabled:
            await self.app(scope, receive, send)
            return
        handler = _find_route_handler(app.routes, scope)
        if _should_exempt(limiter, handler):
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        error_response, inject_headers = await async_check_limits(limiter, request, handler, app)
        if error_response is not None:
            await error_response(scope, receive, send)
            return
        if not inject_headers:
            await self.app(scope, receive, send)
            return

        async def send_with_limit_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                limiter._inject_asgi_headers(  # pyright: ignore[reportPrivateUsage]
                    MutableHeaders(scope=message), request.state.view_rate_limit
                )
            await send(message)

        await self.app(scope, receive, send_with_limit_headers)
