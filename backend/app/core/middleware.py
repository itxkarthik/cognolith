import json
import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Prevent MIME-type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Prevent clickjacking — deny all iframe embedding
        response.headers["X-Frame-Options"] = "DENY"

        # Enable browser XSS filter
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Control referrer information
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Restrict browser feature access
        response.headers[
            "Permissions-Policy"
        ] = "camera=(), microphone=(), geolocation=(), browsing-topics=()"

        # Content Security Policy — restrict resource loading to same origin
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self'; "
            "frame-ancestors 'none'"
        )

        # HSTS — only in staging/production (not local dev)
        if settings.ENVIRONMENT != "local":
            response.headers[
                "Strict-Transport-Security"
            ] = "max-age=63072000; includeSubDomains; preload"

        # Prevent caching of API responses
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"

        return response


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Assigns a unique request ID to every incoming request.

    - If the client sends an `X-Request-ID` header, it is reused.
    - Otherwise, a new UUID4 is generated.
    - The ID is attached to `request.state.request_id` for use in logging/audit.
    - The ID is returned in the `X-Request-ID` response header.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Use client-provided ID or generate a new one
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id

        return response


class MaxRequestBodySizeMiddleware(BaseHTTPMiddleware):
    """
    Rejects requests whose Content-Length header exceeds the configured limit.
    Prevents oversized payloads from consuming server resources.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > settings.MAX_REQUEST_BODY_SIZE:
            return JSONResponse(
                status_code=413,
                content={
                    "detail": f"Request body too large. "
                    f"Maximum: {settings.MAX_REQUEST_BODY_SIZE // (1024 * 1024)} MB"
                },
            )
        return await call_next(request)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Logs all incoming requests and outgoing responses in structured JSON format.

    Features:
    - Captures request details: method, path, query params, headers
    - Captures response details: status code, response time
    - Includes request ID for traceability
    - Uses structured JSON logging for easy parsing
    - Respects LOG_LEVEL configuration
    - Excludes health check endpoints from verbose logging
    """

    # Paths that should use minimal logging (health checks, etc)
    MINIMAL_LOG_PATHS = {"/health", "/health/live", "/health/ready"}

    async def dispatch(self, request: Request, call_next) -> Response:
        # Capture request start time
        start_time = time.time()

        # Get request ID from request state (set by RequestIDMiddleware)
        request_id = getattr(request.state, "request_id", "unknown")

        # Extract request details
        method = request.method
        path = request.url.path
        query_string = str(request.url.query) if request.url.query else None

        # Determine if this should be detailed logging
        is_minimal_path = path in self.MINIMAL_LOG_PATHS

        # Log incoming request
        request_log = {
            "event": "request",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "request_id": request_id,
            "method": method,
            "path": path,
            "query": query_string,
            "client": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent", None),
        }

        if not is_minimal_path:
            logger.debug(json.dumps(request_log))

        try:
            # Call the next middleware/route handler
            response = await call_next(request)
        except Exception as exc:
            # Log errors
            elapsed_time = time.time() - start_time
            error_log = {
                "event": "request_error",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "request_id": request_id,
                "method": method,
                "path": path,
                "query": query_string,
                "client": request.client.host if request.client else None,
                "error": str(exc),
                "error_type": type(exc).__name__,
                "elapsed_ms": round(elapsed_time * 1000, 2),
            }
            logger.error(json.dumps(error_log))
            raise

        # Calculate response time
        elapsed_time = time.time() - start_time

        # Log response
        response_log = {
            "event": "response",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "request_id": request_id,
            "method": method,
            "path": path,
            "status": response.status_code,
            "elapsed_ms": round(elapsed_time * 1000, 2),
        }

        # Use appropriate log level based on status code
        if response.status_code >= 500:
            # Server errors
            logger.error(json.dumps(response_log))
        elif response.status_code >= 400:
            # Client errors
            logger.warning(json.dumps(response_log))
        elif not is_minimal_path:
            # Success logs (except health checks—they're too noisy)
            logger.info(json.dumps(response_log))

        # Add request ID to response headers if not already present
        if "X-Request-ID" not in response.headers:
            response.headers["X-Request-ID"] = request_id

        return response
