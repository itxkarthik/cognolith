"""
pgvector embedding tables.

These are plain tables rather than SQLModel classes: rows are only read and written
through raw SQL in PgVectorStore. Declaring them on the shared metadata keeps
create_all/drop_all (tests) and Alembic in agreement with the migrated schema.
The vector size is fixed by settings.EMBEDDING_DIMENSIONS; changing it needs a
re-index (python -m scripts.reindex_embeddings).
"""

from typing import Any

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Table, Text, func
from sqlalchemy.types import UserDefinedType
from sqlmodel import SQLModel

from app.core.config import settings


class Vector(UserDefinedType[Any]):
    """Column type for pgvector's vector(n); values are bound as text and CAST in SQL."""

    cache_ok = True

    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions

    def get_col_spec(self, **_: Any) -> str:
        return f"vector({self.dimensions})"


def _timestamps() -> list[Column[Any]]:
    return [
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
        Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    ]


def _hnsw_index(name: str) -> Index:
    return Index(
        name,
        "embedding",
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


chunk_embeddings = Table(
    "chunk_embeddings",
    SQLModel.metadata,
    Column(
        "chunk_id",
        Integer,
        ForeignKey("document_chunks.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "document_id", Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    ),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("model", String(100), nullable=False),
    Column("embedding", Vector(settings.EMBEDDING_DIMENSIONS), nullable=False),
    *_timestamps(),
    Index("ix_chunk_embeddings_user_document", "user_id", "document_id"),
    _hnsw_index("ix_chunk_embeddings_embedding_hnsw"),
)

note_embeddings = Table(
    "note_embeddings",
    SQLModel.metadata,
    Column("note_id", Integer, ForeignKey("notes.id", ondelete="CASCADE"), primary_key=True),
    # Notes are split like documents; each passage has its own vector
    Column("chunk_index", Integer, primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("model", String(100), nullable=False),
    # Hash of the whole note and chunk settings; equal on all of a note's rows
    Column("content_hash", String(64), nullable=False),
    Column("content", Text, nullable=False),
    Column("embedding", Vector(settings.EMBEDDING_DIMENSIONS), nullable=False),
    *_timestamps(),
    Index("ix_note_embeddings_user", "user_id", "note_id"),
    _hnsw_index("ix_note_embeddings_embedding_hnsw"),
)

chat_message_embeddings = Table(
    "chat_message_embeddings",
    SQLModel.metadata,
    Column(
        "message_id",
        Integer,
        ForeignKey("chat_messages.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "session_id", Integer, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    ),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("model", String(100), nullable=False),
    Column("content_hash", String(64), nullable=False),
    Column("embedding", Vector(settings.EMBEDDING_DIMENSIONS), nullable=False),
    *_timestamps(),
    Index("ix_chat_message_embeddings_user_session", "user_id", "session_id"),
    _hnsw_index("ix_chat_message_embeddings_embedding_hnsw"),
)

EMBEDDING_TABLES = (chunk_embeddings, note_embeddings, chat_message_embeddings)
