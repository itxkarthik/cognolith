"""Conversation history sent to the model alongside a new question."""

from collections.abc import Sequence
from typing import Any

from app.models.chat import ChatGenerationStatus, ChatMessages, ChatRole

# Metadata key on an assistant message naming the user message it answers
REPLY_TO_KEY = "reply_to_message_id"

# Earlier question-and-answer pairs included in the prompt
HISTORY_TURNS = 3


def build_conversation_history(
    messages: Sequence[ChatMessages], *, turns: int = HISTORY_TURNS
) -> list[dict[str, Any]]:
    """
    Pair each earlier question with its final answer, oldest first.

    `messages` are the chat's messages before the question being answered, in
    chronological order. Failed, cancelled, still-streaming and empty replies are
    left out, a retried question appears once with its last completed answer, and
    questions that never got an answer are dropped so roles strictly alternate.
    """
    answers: dict[int, ChatMessages] = {}
    previous_question_id: int | None = None
    for message in messages:
        if message.role == ChatRole.user:
            previous_question_id = message.id
        elif _is_final_answer(message):
            reply_to = (message.generation_metadata or {}).get(REPLY_TO_KEY)
            # Replies saved before reply_to existed answer the question just before them
            question_id = reply_to if isinstance(reply_to, int) else previous_question_id
            if question_id is not None:
                answers[question_id] = message  # a later completed retry supersedes

    answered = [
        (message, answers[message.id])
        for message in messages
        if message.role == ChatRole.user and message.id in answers and message.content.strip()
    ]
    history: list[dict[str, Any]] = []
    for question, answer in answered[-turns:] if turns > 0 else []:
        history.append(_history_entry(question))
        history.append(_history_entry(answer))
    return history


def _is_final_answer(message: ChatMessages) -> bool:
    # None: replies stored in one piece by the non-streaming path, always complete
    return (
        message.role == ChatRole.assistant
        and message.generation_status in {None, ChatGenerationStatus.completed}
        and bool(message.content.strip())
    )


def _history_entry(message: ChatMessages) -> dict[str, Any]:
    role = message.role.value if isinstance(message.role, ChatRole) else str(message.role)
    return {"role": role, "content": message.content, "sources": message.sources}
