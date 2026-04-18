from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session

from app.ai.llm import LLMService, build_chat_messages
from app.models.document import Document
from app.models.note import NoteFolders, Notes
from app.utils.text_processing import create_content_preview


@dataclass(slots=True)
class GeneratedInsights:
    key_points: list[str]
    action_items: list[str]
    markdown: str


def summarize_document_into_note(
    *,
    session: Session,
    user_id: int,
    document_id: int,
    title: str | None = None,
    folder_id: int | None = None,
) -> Notes:
    document = _get_user_document(session=session, user_id=user_id, document_id=document_id)
    _validate_folder_access(session=session, user_id=user_id, folder_id=folder_id)

    prompt = (
        "Summarize the following document into a structured markdown note with sections: "
        "Overview, Key Concepts, Important Details, and Quick Recap."
    )
    generated_markdown = _generate_markdown(
        session=session, user_id=user_id, prompt=prompt, content=document.content
    )

    note_title = title or f"Summary: {document.title}"
    return _create_ai_note(
        session=session,
        user_id=user_id,
        title=note_title,
        content=generated_markdown,
        linked_document_id=document.id,
        folder_id=folder_id,
    )


def generate_study_notes_from_content(
    *,
    session: Session,
    user_id: int,
    source_content: str,
    title: str,
    folder_id: int | None = None,
) -> Notes:
    if not source_content.strip():
        raise HTTPException(status_code=400, detail="Source content cannot be empty")

    _validate_folder_access(session=session, user_id=user_id, folder_id=folder_id)

    prompt = (
        "Convert the provided content into study notes in markdown with sections: "
        "Core Ideas, Definitions, Examples, Practice Questions, and Revision Checklist."
    )
    generated_markdown = _generate_markdown(
        session=session, user_id=user_id, prompt=prompt, content=source_content
    )

    return _create_ai_note(
        session=session,
        user_id=user_id,
        title=title,
        content=generated_markdown,
        linked_document_id=None,
        folder_id=folder_id,
    )


def extract_key_points_and_action_items(
    *,
    session: Session,
    user_id: int,
    source_content: str,
) -> GeneratedInsights:
    if not source_content.strip():
        raise HTTPException(status_code=400, detail="Source content cannot be empty")

    prompt = (
        "Read the content and produce markdown with two sections only: "
        "1) Key Points (bullet list), 2) Action Items (checkbox list with concise tasks)."
    )
    markdown = _generate_markdown(
        session=session, user_id=user_id, prompt=prompt, content=source_content
    )

    key_points = _extract_bullet_items(markdown=markdown, section_header="Key Points")
    action_items = _extract_bullet_items(markdown=markdown, section_header="Action Items")
    return GeneratedInsights(key_points=key_points, action_items=action_items, markdown=markdown)


def _get_user_document(*, session: Session, user_id: int, document_id: int) -> Document:
    document = session.get(Document, document_id)
    if not document or document.user_id != user_id or document.is_deleted:
        raise HTTPException(status_code=404, detail="Document not found")
    if not document.content:
        raise HTTPException(
            status_code=400, detail="Document has no extracted content to summarize"
        )
    return document


def _validate_folder_access(*, session: Session, user_id: int, folder_id: int | None) -> None:
    if folder_id is None:
        return
    folder = session.get(NoteFolders, folder_id)
    if not folder or folder.user_id != user_id or folder.is_deleted:
        raise HTTPException(status_code=404, detail="Folder not found")


def _create_ai_note(
    *,
    session: Session,
    user_id: int,
    title: str,
    content: str,
    linked_document_id: int | None,
    folder_id: int | None,
) -> Notes:
    clean_title = title.strip() or "AI Generated Note"
    clean_content = content.strip()

    note = Notes(
        user_id=user_id,
        folder_id=folder_id,
        title=clean_title,
        content=clean_content,
        content_type="markdown",
        content_preview=create_content_preview(clean_content, max_length=200),
        linked_document_id=linked_document_id,
        ai_generated=True,
        summary=create_content_preview(clean_content, max_length=300),
        word_count=len(clean_content.split()),
        char_count=len(clean_content),
        read_time_minutes=max(1, len(clean_content.split()) // 200),
    )
    session.add(note)
    session.commit()
    session.refresh(note)
    return note


def _generate_markdown(*, session: Session, user_id: int, prompt: str, content: str) -> str:
    messages = build_chat_messages(
        user_prompt=f"{prompt}\n\nContent:\n{content}",
        system_prompt="You are an expert note-making assistant. Output concise, clean markdown.",
    )
    llm_service = LLMService(session=session, user_id=user_id)
    generated = _run_async(llm_service.generate_response(messages=messages))
    return generated.strip()


def _extract_bullet_items(*, markdown: str, section_header: str) -> list[str]:
    lines = markdown.splitlines()
    header_markers = {f"## {section_header}", f"### {section_header}", f"# {section_header}"}

    in_section = False
    items: list[str] = []

    for raw_line in lines:
        line = raw_line.strip()
        if line in header_markers:
            in_section = True
            continue

        if in_section and line.startswith("#"):
            break

        if in_section and (line.startswith("- ") or line.startswith("* ")):
            items.append(line[2:].strip())
            continue

        if in_section and line.startswith("- ["):
            cleaned = line.split("]", 1)[-1].strip()
            if cleaned:
                items.append(cleaned)

    return items


def _run_async(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(lambda: asyncio.run(coro))
        return future.result()
