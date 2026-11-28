"""The pure ASGI middleware stack: caching, streaming, request ids, CSRF (issue #30)."""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlmodel import Session
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route
from starlette.types import Message

from app import crud
from app.core.cache_middleware import ETagAndCacheMiddleware, etag_matches
from app.core.config import settings
from app.core.csrf import CSRFMiddleware
from app.core.middleware import (
    MaxRequestBodySizeMiddleware,
    RateLimitMiddleware,
    RequestIDMiddleware,
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
)
from app.main import app
from app.models.user import UserCreate

API = settings.API_V1_STR
EMAIL = "middleware@example.com"
PASSWORD = "secure-password"


@pytest.fixture
def client(session: Session) -> TestClient:
    crud.create_user(session=session, user_create=UserCreate(email=EMAIL, password=PASSWORD))
    test_client = TestClient(app)
    test_client.post(
        f"{API}/login/access-token", data={"username": EMAIL, "password": PASSWORD}
    ).raise_for_status()
    return test_client


def _csrf(client: TestClient) -> dict[str, str]:
    return {settings.CSRF_HEADER_NAME: client.cookies.get(settings.CSRF_COOKIE_NAME) or ""}


def test_private_data_is_never_publicly_cacheable(client: TestClient) -> None:
    for path in ("/notes/", "/documents/", "/chat/sessions"):
        response = client.get(API + path)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "private, no-cache"
        assert response.headers["etag"].startswith('"')


def test_an_unchanged_list_revalidates_to_304_and_a_change_does_not(client: TestClient) -> None:
    first = client.get(f"{API}/notes/")
    etag = first.headers["etag"]

    unchanged = client.get(f"{API}/notes/", headers={"If-None-Match": etag})
    assert unchanged.status_code == 304
    assert unchanged.content == b""
    assert unchanged.headers["etag"] == etag

    client.post(
        f"{API}/notes/", json={"title": "New", "content": "body"}, headers=_csrf(client)
    ).raise_for_status()
    changed = client.get(f"{API}/notes/", headers={"If-None-Match": etag})
    assert changed.status_code == 200
    assert changed.headers["etag"] != etag


def test_writes_and_errors_are_not_stored(client: TestClient) -> None:
    created = client.post(
        f"{API}/notes/", json={"title": "New", "content": "body"}, headers=_csrf(client)
    )
    missing = client.get(f"{API}/notes/999999")
    for response in (created, missing):
        assert response.headers["cache-control"] == "no-cache, no-store, must-revalidate"
        assert "etag" not in response.headers


def test_if_none_match_follows_rfc_9110() -> None:
    assert etag_matches('W/"abc", "def"', '"abc"')
    assert etag_matches("*", '"abc"')
    assert not etag_matches('"other"', '"abc"')
    assert not etag_matches(None, '"abc"')


def test_security_headers_and_request_id_on_every_response(client: TestClient) -> None:
    response = client.get(f"{API}/notes/", headers={"X-Request-ID": "trace-123"})
    assert response.headers["x-request-id"] == "trace-123"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize("supplied", ["bad\r\nInjected: yes", "x" * 129, "spaces not allowed"])
def test_an_unsafe_request_id_is_replaced(client: TestClient, supplied: str) -> None:
    response = client.get("/health/live", headers={"X-Request-ID": supplied})
    assert response.headers["x-request-id"] != supplied
    assert len(response.headers["x-request-id"]) == 36  # a fresh UUID


def test_log_lines_carry_the_request_id(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="app.core.middleware"):
        client.get(f"{API}/notes/", headers={"X-Request-ID": "trace-456"})
    responses = [
        json.loads(record.getMessage())
        for record in caplog.records
        if record.getMessage().startswith('{"event": "response"')
    ]
    assert [entry["request_id"] for entry in responses] == ["trace-456"]


def test_a_client_without_a_csrf_token_gets_one_once(session: Session) -> None:
    fresh = TestClient(app)
    first = fresh.get("/")
    assert settings.CSRF_COOKIE_NAME in first.cookies
    again = fresh.get("/")
    assert settings.CSRF_COOKIE_NAME not in again.headers.get("set-cookie", "")


def test_a_write_without_the_csrf_header_is_refused(client: TestClient) -> None:
    response = client.post(f"{API}/notes/", json={"title": "New", "content": "body"})
    assert response.status_code == 403
    assert response.headers["x-csrf-error"] == "invalid_token"
    # Refusals still get the security headers and a request id
    assert response.headers["x-frame-options"] == "DENY"
    assert "x-request-id" in response.headers


# --- streaming through the whole stack -------------------------------------------


def _stack(inner: Starlette) -> object:
    """The production middleware order, around a test app."""
    wrapped: object = inner
    for middleware in (
        ETagAndCacheMiddleware,
        CSRFMiddleware,
        RateLimitMiddleware,
        MaxRequestBodySizeMiddleware,
        SecurityHeadersMiddleware,
        RequestLoggingMiddleware,
        RequestIDMiddleware,
    ):
        wrapped = middleware(wrapped)  # pyright: ignore[reportArgumentType]
    return wrapped


@pytest.mark.asyncio
async def test_a_stream_passes_through_chunk_by_chunk() -> None:
    produced: list[int] = []
    release = asyncio.Event()

    async def chunks() -> AsyncIterator[str]:
        for index in range(3):
            produced.append(index)
            yield f"data: {index}\n\n"
            if index == 0:
                # Hold the stream: the first chunk must already be out
                await release.wait()

    async def stream(_: Request) -> StreamingResponse:
        return StreamingResponse(chunks(), media_type="text/event-stream")

    async def limited(_: Request) -> JSONResponse:
        return JSONResponse({"ok": True})

    inner = Starlette(routes=[Route("/stream", stream), Route("/json", limited)])
    inner.state.limiter = Limiter(
        key_func=get_remote_address, default_limits=["100/minute"], headers_enabled=True
    )
    stack = _stack(inner)

    sent: list[Message] = []
    first_chunk_seen = asyncio.Event()

    async def send(message: Message) -> None:
        sent.append(message)
        if message["type"] == "http.response.body" and message.get("body"):
            first_chunk_seen.set()

    request_sent = False

    async def receive() -> Message:
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await asyncio.Event().wait()  # no disconnect
        raise AssertionError("unreachable")

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/stream",
        "raw_path": b"/stream",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 1),
        "server": ("test", 80),
        "scheme": "http",
        "root_path": "",
        "app": inner,
        "http_version": "1.1",
    }
    running = asyncio.create_task(stack(scope, receive, send))  # pyright: ignore[reportCallIssue]
    await asyncio.wait_for(first_chunk_seen.wait(), timeout=2)
    assert produced == [0]  # delivered before the generator went on
    release.set()
    await asyncio.wait_for(running, timeout=2)

    starts = [message for message in sent if message["type"] == "http.response.start"]
    assert len(starts) == 1
    headers = dict((k.decode(), v.decode()) for k, v in starts[0]["headers"])
    assert headers["cache-control"] == "no-cache, no-store, no-transform"
    assert "x-ratelimit-limit" in headers
    bodies = [message.get("body") for message in sent if message["type"] == "http.response.body"]
    assert [body for body in bodies if body] == [b"data: 0\n\n", b"data: 1\n\n", b"data: 2\n\n"]


@pytest.mark.parametrize(
    "chunks",
    [
        [b'"' + b"x" * 200 + b'"'],  # one body message
        [b'"' + b"x" * 50, b"x" * 150 + b'"'],  # the last chunk crosses the cap
    ],
)
def test_a_body_over_the_cap_is_sent_without_hashing(
    monkeypatch: pytest.MonkeyPatch, chunks: list[bytes]
) -> None:
    from app.core import cache_middleware

    def no_hashing(_: bytes) -> str:
        raise AssertionError("hashed a body over the cap")

    monkeypatch.setattr(cache_middleware, "make_etag", no_hashing)

    async def inner(scope: Any, receive: Any, send: Any) -> None:
        # Raw messages, the last one carrying data, as a plain JSON response sends
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        for index, chunk in enumerate(chunks):
            more_body = index < len(chunks) - 1
            await send({"type": "http.response.body", "body": chunk, "more_body": more_body})

    client = TestClient(ETagAndCacheMiddleware(inner, max_etag_body_bytes=100))

    response = client.get("/big")

    assert response.content == b"".join(chunks)
    assert "etag" not in response.headers
    assert response.headers["cache-control"] == cache_middleware.NO_STORE
