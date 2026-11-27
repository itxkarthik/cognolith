"""Only finished question-and-answer pairs reach the model as history (issue #14)."""

from itertools import count

from app.models.chat import ChatGenerationStatus, ChatMessages, ChatRole
from app.services.chat_history import REPLY_TO_KEY, build_conversation_history

_ids = count(1)


def _question(content: str) -> ChatMessages:
    return ChatMessages(id=next(_ids), session_id=1, role=ChatRole.user, content=content)


def _answer(
    content: str,
    question: ChatMessages | None = None,
    status: ChatGenerationStatus | None = ChatGenerationStatus.completed,
) -> ChatMessages:
    metadata = {REPLY_TO_KEY: question.id} if question is not None else None
    return ChatMessages(
        id=next(_ids),
        session_id=1,
        role=ChatRole.assistant,
        content=content,
        generation_status=status,
        generation_metadata=metadata,
    )


def _contents(messages: list[ChatMessages]) -> list[tuple[str, str]]:
    return [(entry["role"], entry["content"]) for entry in build_conversation_history(messages)]


def test_failed_cancelled_streaming_and_empty_replies_are_left_out() -> None:
    q1 = _question("What is RAG?")
    messages = [
        q1,
        _answer("Retrieval-augm", q1, ChatGenerationStatus.failed),
        _answer("Retrieval", q1, ChatGenerationStatus.cancelled),
        _answer("   ", q1),
        _answer("Retrieval-augmented generation.", q1),
        _answer("Draft in progress", q1, ChatGenerationStatus.streaming),
    ]

    assert _contents(messages) == [
        ("user", "What is RAG?"),
        ("assistant", "Retrieval-augmented generation."),
    ]


def test_a_retried_question_appears_once_with_its_final_answer() -> None:
    q1 = _question("Summarize my notes")
    q2 = _question("And the documents?")
    messages = [
        q1,
        _answer("Partial", q1, ChatGenerationStatus.failed),
        q2,
        _answer("Documents summary", q2),
        # Retry of q1 finished after q2 was answered
        _answer("Notes summary", q1),
    ]

    assert _contents(messages) == [
        ("user", "Summarize my notes"),
        ("assistant", "Notes summary"),
        ("user", "And the documents?"),
        ("assistant", "Documents summary"),
    ]


def test_unanswered_questions_are_dropped_so_roles_alternate() -> None:
    q1 = _question("First")
    q2 = _question("Second")
    messages = [q1, _answer("", q1, ChatGenerationStatus.failed), q2, _answer("Two", q2)]

    assert _contents(messages) == [("user", "Second"), ("assistant", "Two")]


def test_replies_saved_before_reply_to_existed_pair_with_the_previous_question() -> None:
    q1 = _question("Legacy question")
    messages = [q1, _answer("Legacy answer", status=None)]

    assert _contents(messages) == [("user", "Legacy question"), ("assistant", "Legacy answer")]


def test_only_the_most_recent_turns_are_kept() -> None:
    messages: list[ChatMessages] = []
    for number in range(5):
        question = _question(f"Q{number}")
        messages += [question, _answer(f"A{number}", question)]

    history = _contents(messages)

    assert [content for _, content in history] == ["Q2", "A2", "Q3", "A3", "Q4", "A4"]
