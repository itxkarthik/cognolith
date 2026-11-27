"""How documents and notes are split into the passages that are embedded and cited."""

import hashlib
from dataclasses import dataclass

from sqlmodel import Session

from app.models.note import Notes
from app.models.user import UserSettings
from app.utils.text_processing import split_text_into_chunks


def chunking_preferences(session: Session, user_id: int) -> tuple[int, int]:
    """The user's chunk size/overlap, with overlap kept below the size it slides over."""
    preferences = session.get(UserSettings, user_id) or UserSettings(user_id=user_id)
    chunk_size = preferences.chunk_size
    return chunk_size, min(preferences.chunk_overlap, chunk_size // 2)


@dataclass(frozen=True, slots=True)
class NoteChunk:
    note_id: int
    chunk_index: int
    # The passage itself, returned by search and cited in answers
    content: str
    # What is embedded: the passage under the note's title, so every vector keeps the subject
    embedding_text: str
    # Identifies the note text and chunk settings the whole set of chunks was built from
    content_hash: str


def chunk_note(note: Notes, *, chunk_size: int, overlap: int) -> list[NoteChunk]:
    """Split a note into overlapping passages; empty when it has no text at all."""
    if note.id is None:
        raise ValueError("Note must be persisted before it is chunked")
    title = note.title.strip()
    passages = split_text_into_chunks(note.content, chunk_size=chunk_size, overlap=overlap)
    if not passages and title:
        passages = [title]
    content_hash = hashlib.sha256(
        f"{chunk_size}:{overlap}\n{title}\n\n{note.content}".encode()
    ).hexdigest()
    return [
        NoteChunk(
            note_id=note.id,
            chunk_index=index,
            content=passage,
            embedding_text=f"{title}\n\n{passage}" if title and passage != title else passage,
            content_hash=content_hash,
        )
        for index, passage in enumerate(passages)
    ]
