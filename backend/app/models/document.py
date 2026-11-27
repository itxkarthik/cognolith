from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar
from uuid import UUID, uuid4

from sqlalchemy import ARRAY, DateTime, String, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Column, Field, Index, Relationship, SQLModel, UniqueConstraint

from .chat import TimestampMixin
from .portable import PortableIdMixin

if TYPE_CHECKING:
    from .note import Notes
    from .user import User


class DocumentStatus(StrEnum):
    processing = "processing"
    completed = "completed"
    failed = "failed"
    deleted = "deleted"


class DocumentEmbeddingStatus(StrEnum):
    # Not embedded yet: still processing, or processing failed before embedding
    pending = "pending"
    # Every chunk has a vector (a document with no text has nothing to embed)
    indexed = "indexed"
    # Embedding failed; content is stored and the next search or chat retries it
    failed = "failed"


class Document(PortableIdMixin, TimestampMixin, SQLModel, table=True):
    __tablename__: ClassVar[str] = "documents"  # pyright: ignore
    __table_args__ = (
        Index("ix_document_user_created", "user_id", "created_at"),
        Index("ix_documents_user_status", "user_id", "status"),
        Index("ix_document_tags", "tags", postgresql_using="gin"),
    )
    id: int | None = Field(default=None, primary_key=True)
    portable_id: UUID = Field(
        default_factory=uuid4,
        sa_column=Column(PGUUID(as_uuid=True), nullable=False, unique=True, index=True),
    )
    user_id: int | None = Field(foreign_key="users.id", ondelete="CASCADE", nullable=False)
    title: str = Field(nullable=False, max_length=255)
    file_name: str = Field(nullable=False, max_length=255)
    file_path: str = Field(nullable=False)
    file_size: int = Field(nullable=False)
    file_type: str = Field(nullable=False, max_length=255, index=True)
    mime_type: str = Field(nullable=False, max_length=255)
    is_deleted: bool = Field(default=False)
    content: str | None = Field(default=None)
    content_preview: str | None = Field(default=None, max_length=500)
    summary: str | None = Field(default=None)  # TEXT not ARRAY
    keywords: list[str] = Field(default_factory=list, sa_column=Column(ARRAY(String)))
    tags: list[str] = Field(default_factory=list, sa_column=Column(ARRAY(String)))
    language: str = Field(default="en", max_length=10)
    status: str = Field(default="processing", max_length=50)
    processing_started_at: datetime | None = Field(default=None)
    processing_completed_at: datetime | None = Field(default=None)
    processing_error: str | None = Field(default=None)
    # Runs started, so a file that crashes the process isn't retried forever
    processing_attempts: int = Field(default=0)
    # Held by the backend process running this document; past it, any process may
    # claim it. Written and compared with the database clock only.
    processing_lease_until: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    # Identifies the current lease, so a holder that lost it can't renew or free it
    processing_lease_token: str | None = Field(default=None, max_length=32)
    embedding_status: DocumentEmbeddingStatus = Field(
        default=DocumentEmbeddingStatus.pending,
        sa_column=Column(String(20), nullable=False, server_default="pending"),
    )
    word_count: int | None = Field(default=None)
    page_count: int | None = Field(default=None)
    chunk_count: int = Field(default=0)
    last_accessed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Relationships
    user: "User" = Relationship(back_populates="documents")
    chunks: list["DocumentChunks"] = Relationship(
        back_populates="document",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "order_by": "DocumentChunks.chunk_index",
        },
    )
    linked_notes: list["Notes"] = Relationship(
        back_populates="linked_document",
        sa_relationship_kwargs={"foreign_keys": "[Notes.linked_document_id]"},
    )


class DocumentChunks(TimestampMixin, SQLModel, table=True):
    __tablename__: ClassVar[str] = "document_chunks"  # pyright: ignore
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uix_document_chunks"),
        Index(
            "ix_document_chunks_content_trgm",
            text("lower(content) gin_trgm_ops"),
            postgresql_using="gin",
        ),
    )
    id: int | None = Field(default=None, primary_key=True, index=True)
    document_id: int | None = Field(foreign_key="documents.id", ondelete="CASCADE", nullable=False)
    chunk_index: int | None = Field(nullable=False)
    content: str = Field(nullable=False)
    content_hash: str | None = Field(default=None, max_length=255)
    vector_id: str = Field(nullable=False, index=True)
    token_count: int | None = Field(default=None)
    char_count: int | None = Field(default=None)
    page_number: int | None = Field(default=None)
    section_title: str | None = Field(default=None, max_length=255)

    # Relationships
    document: Document = Relationship(back_populates="chunks")
