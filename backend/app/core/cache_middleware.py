"""
Cache headers and ETags for API responses, as pure ASGI middleware.

API responses belong to the signed-in user, so none may be stored by a shared cache.
A JSON 200 to a GET is sent `private, no-cache` with an ETag: the browser keeps it
but asks again every time, and gets an empty 304 when nothing changed. Everything
else is `no-store`, and event streams also forbid transformation so a proxy can't
compress (and so buffer) them.
"""

import hashlib

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REVALIDATE = "private, no-cache"
NO_STORE = "no-cache, no-store, must-revalidate"
EVENT_STREAM = "no-cache, no-store, no-transform"
# Larger bodies are sent without an ETag rather than held in memory to hash
MAX_ETAG_BODY_BYTES = 4 * 1024 * 1024
# Dropped from a 304, which carries no body
_BODY_HEADERS = {"content-length", "content-type", "content-encoding"}


def make_etag(body: bytes) -> str:
    return f'"{hashlib.sha256(body).hexdigest()}"'


def etag_matches(if_none_match: str | None, etag: str) -> bool:
    """RFC 9110 If-None-Match: weak comparison over a list of tags, or `*`."""
    if not if_none_match:
        return False
    candidates = {tag.strip().removeprefix("W/") for tag in if_none_match.split(",")}
    return "*" in candidates or etag in candidates


class ETagAndCacheMiddleware:
    def __init__(self, app: ASGIApp, max_etag_body_bytes: int = MAX_ETAG_BODY_BYTES) -> None:
        self.app = app
        self.max_etag_body_bytes = max_etag_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if_none_match = Headers(scope=scope).get("if-none-match")
        is_get = scope["method"] == "GET"
        start: Message | None = None
        buffered: list[bytes] = []
        size = 0
        fingerprinting = False

        async def flush_unfingerprinted(more_body: bool) -> None:
            # Too large to hash: send what was held, then stream any rest as-is
            nonlocal fingerprinting, start
            fingerprinting = False
            assert start is not None
            MutableHeaders(scope=start)["Cache-Control"] = NO_STORE
            await send(start)
            start = None
            await send(
                {"type": "http.response.body", "body": b"".join(buffered), "more_body": more_body}
            )
            buffered.clear()

        async def send_with_cache_headers(message: Message) -> None:
            nonlocal start, size, fingerprinting
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                content_type = headers.get("content-type", "")
                if content_type.startswith("text/event-stream"):
                    headers["Cache-Control"] = EVENT_STREAM
                elif "cache-control" not in headers:
                    if (
                        is_get
                        and message["status"] == 200
                        and content_type.startswith("application/json")
                    ):
                        # Held until the body is complete, to hash it
                        start = message
                        fingerprinting = True
                        return
                    headers["Cache-Control"] = NO_STORE
                    headers.setdefault("Pragma", "no-cache")
                await send(message)
                return

            if not fingerprinting or message["type"] != "http.response.body":
                await send(message)
                return
            body = message.get("body", b"")
            buffered.append(body)
            size += len(body)
            more_body = message.get("more_body", False)
            # Checked for the final message too: a whole response may come in one
            if size > self.max_etag_body_bytes:
                await flush_unfingerprinted(more_body)
                return
            if more_body:
                return

            fingerprinting = False
            assert start is not None
            payload = b"".join(buffered)
            etag = make_etag(payload)
            headers = MutableHeaders(scope=start)
            headers["Cache-Control"] = REVALIDATE
            headers["ETag"] = etag
            if etag_matches(if_none_match, etag):
                start["status"] = 304
                start["headers"] = [
                    (name, value)
                    for name, value in headers.raw
                    if name.decode("latin-1") not in _BODY_HEADERS
                ]
                await send(start)
                await send({"type": "http.response.body", "body": b"", "more_body": False})
                return
            await send(start)
            await send({"type": "http.response.body", "body": payload, "more_body": False})

        await self.app(scope, receive, send_with_cache_headers)
