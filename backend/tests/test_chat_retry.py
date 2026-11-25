from sqlmodel import Session

from app import crud
from app.models.chat import ChatGenerationStatus, ChatMessages, ChatSession
from app.models.user import User, UserCreate
from app.services.chat_generation import (
    REPLY_TO_KEY,
    create_generation_messages,
    create_retry_message,
    generation_coordinator,
)


def _context(session: Session) -> tuple[User, ChatSession]:
    user = crud.create_user(
        session=session,
        user_create=UserCreate(email="retry@example.com", password="secure-password"),
    )
    chat_session = ChatSession(user_id=user.id, title="Retry")
    session.add(chat_session)
    session.commit()
    session.refresh(chat_session)
    return user, chat_session


def _finish(session: Session, message: ChatMessages, status: ChatGenerationStatus) -> None:
    assert message.id is not None and message.session_id is not None
    generation_coordinator.finish(session_id=message.session_id, message_id=message.id)
    message.generation_status = status
    session.add(message)
    session.commit()


def test_retry_answers_the_original_question_after_the_thread_moved_on(
    session: Session,
) -> None:
    user, chat_session = _context(session)
    first_question, first_reply, _ = create_generation_messages(
        session=session, user=user, chat_session=chat_session, content="First question"
    )
    _finish(session, first_reply, ChatGenerationStatus.failed)
    _, second_reply, _ = create_generation_messages(
        session=session, user=user, chat_session=chat_session, content="Second question"
    )
    _finish(session, second_reply, ChatGenerationStatus.completed)

    assert first_reply.id is not None
    retried_question, retry, _ = create_retry_message(
        session=session, user=user, chat_session=chat_session, failed_message_id=first_reply.id
    )
    _finish(session, retry, ChatGenerationStatus.failed)

    assert retried_question.id == first_question.id
    assert retry.generation_metadata is not None
    assert retry.generation_metadata[REPLY_TO_KEY] == first_question.id

    # Retrying the retry still answers the first question
    assert retry.id is not None
    again_question, again, _ = create_retry_message(
        session=session, user=user, chat_session=chat_session, failed_message_id=retry.id
    )
    _finish(session, again, ChatGenerationStatus.failed)

    assert again_question.id == first_question.id
