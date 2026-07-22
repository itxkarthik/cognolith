from datetime import UTC, datetime, timedelta
from typing import cast
from unittest import TestCase

import pytest
from fastapi import WebSocket
from pydantic import ValidationError
from sqlmodel import Session

from app import crud
from app.api.routes.chat import (
    _authenticate_websocket,
    _is_allowed_websocket_origin,
    _parse_websocket_message,
    _stream_generated_chat_response,
    _to_chat_message_response,
)
from app.core import security
from app.core.config import settings
from app.models.chat import ChatGenerationStatus, ChatMessages, ChatRole, ChatSession
from app.models.user import UserCreate
from app.services.chat_generation import encode_sse


class FakeWebSocket:
    def __init__(self, *, token: str | None, origin: str | None = None) -> None:
        self.headers = {"origin": origin or settings.FRONTEND_HOST}
        self.cookies = {settings.ACCESS_TOKEN_COOKIE_NAME: token} if token else {}
        self.closed: tuple[int, str] | None = None

    async def close(self, code: int, reason: str) -> None:
        self.closed = (code, reason)


class ChatRouteSerializationTests(TestCase):
    def test_serializes_enum_role_as_api_value(self) -> None:
        now = datetime.now(UTC)
        message = ChatMessages(
            id=1,
            session_id=2,
            role=ChatRole.user,
            content="Hello",
            created_at=now,
            updated_at=now,
        )

        response = _to_chat_message_response(message)

        self.assertEqual(response.role, "user")

    def test_serializes_assistant_generation_lifecycle(self) -> None:
        now = datetime.now(UTC)
        message = ChatMessages(
            id=3,
            session_id=2,
            role=ChatRole.assistant,
            content="Partial",
            generation_status=ChatGenerationStatus.cancelled,
            generation_error=None,
            generation_metadata={"repair_attempted": False},
            generation_started_at=now,
            generation_completed_at=now,
            created_at=now,
            updated_at=now,
        )

        response = _to_chat_message_response(message)

        assert response.generation_status == "cancelled"
        assert response.generation_metadata == {"repair_attempted": False}


def test_structured_sse_uses_named_json_event() -> None:
    event = encode_sse("token", {"message_id": 2, "delta": "hello\nworld"})

    assert event.startswith("event: token\n")
    assert '"delta":"hello\\nworld"' in event
    assert event.endswith("\n\n")


@pytest.mark.asyncio
async def test_generated_chat_stream_opens_before_generation_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def generated_events(**_: object):
        yield encode_sse("token", {"message_id": 2, "delta": "Ready"})
        yield encode_sse("completed", {"message": {"id": 2}})

    monkeypatch.setattr("app.api.routes.chat.stream_chat_generation", generated_events)
    stream = _stream_generated_chat_response(
        user_id=1,
        session_id=1,
        user_message_id=1,
        assistant_message_id=2,
    )

    assert await anext(stream) == ": connected\n\n"
    remaining = [event async for event in stream]
    assert remaining[0].startswith("event: token")
    assert remaining[-1].startswith("event: completed")


def test_websocket_origin_must_match_configured_frontend() -> None:
    assert _is_allowed_websocket_origin(settings.FRONTEND_HOST)
    assert not _is_allowed_websocket_origin("https://attacker.example")
    assert not _is_allowed_websocket_origin(None)


def test_websocket_message_accepts_bounded_nonempty_content() -> None:
    message = _parse_websocket_message('{"type":"message","content":" Hello "}')

    assert message.content == "Hello"


@pytest.mark.parametrize(
    "payload",
    [
        '{"type":"message","content":"   "}',
        '{"type":"admin","content":"hello"}',
        '{"type":"message","content":"hello","sender_id":999}',
    ],
)
def test_websocket_message_rejects_invalid_payload(payload: str) -> None:
    with pytest.raises(ValidationError):
        _parse_websocket_message(payload)


def test_websocket_message_rejects_oversized_frame() -> None:
    payload = '{"type":"message","content":"' + ("x" * settings.WEBSOCKET_MAX_MESSAGE_SIZE) + '"}'

    with pytest.raises(ValueError, match="too large"):
        _parse_websocket_message(payload)


@pytest.mark.asyncio
async def test_websocket_authentication_allows_only_session_owner(session: Session) -> None:
    owner = crud.create_user(
        session=session,
        user_create=UserCreate(email="ws-owner@example.com", password="secure-password"),
    )
    other = crud.create_user(
        session=session,
        user_create=UserCreate(email="ws-other@example.com", password="secure-password"),
    )
    chat_session = ChatSession(user_id=owner.id, title="Private chat")
    session.add(chat_session)
    session.commit()
    session.refresh(chat_session)
    assert owner.id is not None and other.id is not None and chat_session.id is not None

    owner_token = security.create_access_token(subject=owner.id, expires_delta=timedelta(minutes=5))
    other_token = security.create_access_token(subject=other.id, expires_delta=timedelta(minutes=5))
    owner_socket = FakeWebSocket(token=owner_token)
    other_socket = FakeWebSocket(token=other_token)
    anonymous_socket = FakeWebSocket(token=None)

    assert await _authenticate_websocket(cast(WebSocket, owner_socket), chat_session.id) == owner.id
    assert await _authenticate_websocket(cast(WebSocket, other_socket), chat_session.id) is None
    assert other_socket.closed and other_socket.closed[0] == 4403
    assert await _authenticate_websocket(cast(WebSocket, anonymous_socket), chat_session.id) is None
    assert anonymous_socket.closed and anonymous_socket.closed[0] == 4401
