from __future__ import annotations

from sqlmodel import Session

from app.ai.llm import LLMService

MAX_SUMMARY_INPUT_CHARS = 18000


def build_summary_input(content: str, *, max_chars: int = MAX_SUMMARY_INPUT_CHARS) -> str:
    text = content.strip()
    if len(text) <= max_chars:
        return text

    section_size = max_chars // 3
    middle_start = max(0, (len(text) - section_size) // 2)
    return "\n\n".join(
        (
            "[Beginning]\n" + text[:section_size],
            "[Middle]\n" + text[middle_start : middle_start + section_size],
            "[End]\n" + text[-section_size:],
        )
    )


async def generate_document_summary(
    *, session: Session, user_id: int, title: str, content: str
) -> str:
    summary_input = build_summary_input(content)
    if not summary_input:
        raise ValueError("Cannot summarize an empty document")

    messages = [
        {
            "role": "system",
            "content": (
                "You summarize documents for a personal knowledge workspace. Use only facts stated "
                "in the supplied text. Write one concise overview paragraph followed by at most five "
                "key-point bullets. Never infer or invent decisions, plans, owners, tasks, features, "
                "or conclusions. Omit anything the source does not explicitly contain, preserve exact "
                "names, and do not mention that the text was sampled."
            ),
        },
        {
            "role": "user",
            "content": f"Document title: {title}\n\nDocument text:\n{summary_input}",
        },
    ]
    summary = await LLMService(session=session, user_id=user_id).generate_response(
        messages=messages,
        temperature=0.1,
        max_tokens=250,
    )
    result = summary.strip()
    if not result:
        raise ValueError("The model returned an empty document summary")
    return result
