from types import SimpleNamespace
from typing import cast
from unittest import TestCase
from unittest.mock import patch

from fastapi import HTTPException
from sqlmodel import Session

from app.core.exceptions import AIServiceUnavailableError
from app.models.user import User
from app.schemas.chat import ChatMessageCreate
from app.services.chat_service import send_message_and_get_response


class FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.commit_count = 0
        self.rollback_count = 0

    def add(self, value: object) -> None:
        self.added.append(value)

    def commit(self) -> None:
        self.commit_count += 1

    def rollback(self) -> None:
        self.rollback_count += 1

    def refresh(self, _: object) -> None:
        return None


def _chat_context() -> tuple[FakeSession, SimpleNamespace, SimpleNamespace]:
    return (
        FakeSession(),
        SimpleNamespace(id=1),
        SimpleNamespace(id=7, title="Test chat", last_message_at=None),
    )


class ChatServiceTests(TestCase):
    def test_unavailable_ai_does_not_persist_partial_conversation(self) -> None:
        session, current_user, chat_session = _chat_context()

        with (
            patch(
                "app.services.chat_service.get_chat_session_by_id",
                return_value=chat_session,
            ),
            patch(
                "app.services.chat_service._invoke_rag",
                side_effect=ConnectionError("Ollama is down"),
            ),
            patch("app.services.chat_service._acquire_chat_generation_lock"),
        ):
            with self.assertRaises(AIServiceUnavailableError):
                send_message_and_get_response(
                    session=cast(Session, session),
                    current_user=cast(User, current_user),
                    chat_session_id=chat_session.id,
                    payload=ChatMessageCreate(content="Hello", role="user"),
                )

        self.assertEqual(session.added, [])
        self.assertEqual(session.commit_count, 0)
        self.assertEqual(session.rollback_count, 1)

    def test_successful_chat_commits_user_and_assistant_together(self) -> None:
        session, current_user, chat_session = _chat_context()

        with (
            patch(
                "app.services.chat_service.get_chat_session_by_id",
                return_value=chat_session,
            ),
            patch(
                "app.services.chat_service._invoke_rag",
                return_value=("Grounded answer", {"documents": [], "chunks": []}),
            ),
            patch("app.services.chat_service._acquire_chat_generation_lock"),
        ):
            user_message, assistant_message = send_message_and_get_response(
                session=cast(Session, session),
                current_user=cast(User, current_user),
                chat_session_id=chat_session.id,
                payload=ChatMessageCreate(content="Hello", role="user"),
            )

        self.assertEqual(user_message.content, "Hello")
        self.assertEqual(assistant_message.content, "Grounded answer")
        self.assertEqual(session.commit_count, 1)
        self.assertEqual(session.rollback_count, 0)
        self.assertEqual(session.added, [user_message, assistant_message, chat_session])

    def test_concurrent_send_is_rejected_before_rag_runs(self) -> None:
        session, current_user, chat_session = _chat_context()

        with (
            patch(
                "app.services.chat_service.get_chat_session_by_id",
                return_value=chat_session,
            ),
            patch(
                "app.services.chat_service._acquire_chat_generation_lock",
                side_effect=HTTPException(
                    status_code=409,
                    detail="A reply is already being generated for this chat session.",
                ),
            ),
            patch("app.services.chat_service._invoke_rag") as invoke_rag,
        ):
            with self.assertRaises(HTTPException) as raised:
                send_message_and_get_response(
                    session=cast(Session, session),
                    current_user=cast(User, current_user),
                    chat_session_id=chat_session.id,
                    payload=ChatMessageCreate(content="Hello", role="user"),
                )

        self.assertEqual(raised.exception.status_code, 409)
        invoke_rag.assert_not_called()
        self.assertEqual(session.added, [])
        self.assertEqual(session.commit_count, 0)
