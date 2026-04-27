"""ETag and cache control middleware."""

from collections.abc import Callable

from app.utils.etag_utils import generate_etag, get_cache_duration, should_cache_request
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response, StreamingResponse


class ETagAndCacheMiddleware(BaseHTTPMiddleware):
    """
    Middleware for adding ETag and cache control headers to responses.

    Features:
    - Generates ETag for GET responses
    - Adds Cache-Control headers based on endpoint type
    - Handles If-None-Match requests with 304 Not Modified
    - Skips ETag generation for streaming responses
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and add caching headers."""
        response = await call_next(request)

        # Only process GET requests
        if request.method != "GET":
            # Add no-cache for POST, PUT, DELETE, PATCH
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            return response

        # Skip ETag generation for streaming responses
        if isinstance(response, StreamingResponse):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            return response

        # Check if response is cacheable
        if not should_cache_request(request.method, response.status_code):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            return response

        # Determine cache policy based on endpoint
        endpoint_path = request.url.path
        if "/search" in endpoint_path:
            endpoint_type = "search"
        elif any(x in endpoint_path for x in ["notes", "documents", "chat"]):
            if endpoint_path.endswith("/"):
                endpoint_type = "list"
            else:
                endpoint_type = "detail"
        else:
            endpoint_type = "list"

        cache_control, max_age = get_cache_duration(endpoint_type)
        response.headers["Cache-Control"] = cache_control

        # Generate ETag from response body (skip for streaming)
        if response.status_code == 200 and not hasattr(response, "body_iterator"):
            try:
                # For non-streaming responses, generate ETag
                if hasattr(response, "body"):
                    body = response.body
                    if isinstance(body, bytes):
                        etag = generate_etag(body.decode("utf-8"))
                        response.headers["ETag"] = etag

                        # Check If-None-Match header
                        if_none_match = request.headers.get("If-None-Match")
                        if if_none_match and if_none_match == etag:
                            # Return 304 Not Modified
                            return Response(status_code=304, headers=response.headers)
            except Exception:
                # If ETag generation fails, return response as-is
                pass

        return response

        return response
