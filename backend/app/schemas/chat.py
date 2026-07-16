from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils.sanitization import sanitize_plain_text
from app.utils.validators import validate_no_sql_injection, validate_no_xss


class ChatCreate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    description: str | None = None

    @field_validator("title", "description", mode="before")
    @classmethod
    def sanitize_strings(cls, value: str | None) -> str | None:
        if value is None:
            return value
        validate_no_xss(value)
        validate_no_sql_injection(value)
        return sanitize_plain_text(value)


class ChatMessageCreate(BaseModel):
    content: str = Field(min_length=1)
    role: Literal["user", "assistant", "system"] = "user"

    @field_validator("content", mode="before")
    @classmethod
    def sanitize_content(cls, value: str) -> str:
        validate_no_xss(value)
        validate_no_sql_injection(value)
        return sanitize_plain_text(value)


class ChatSourceDocument(BaseModel):
    document_id: int
    title: str
    chunk_count: int
    max_score: float | None
    citation_ids: list[int] = Field(default_factory=list)
    origin: Literal["vector", "inventory", "lexical", "hybrid"] = "vector"


class ChatSourceChunk(BaseModel):
    chunk_id: int
    document_id: int
    document_title: str
    chunk_index: int
    chunk_end_index: int | None = None
    score: float | None
    hybrid_score: float | None = None
    preview: str
    citation_id: int | None = None
    origin: Literal["vector", "inventory", "lexical", "hybrid"] = "vector"


class ChatSourceNote(BaseModel):
    note_id: int
    title: str
    score: float | None
    hybrid_score: float | None = None
    preview: str
    citation_id: int | None = None
    origin: Literal["vector", "inventory", "lexical", "hybrid"] = "vector"


class ChatSources(BaseModel):
    documents: list[ChatSourceDocument] = Field(default_factory=list)
    chunks: list[ChatSourceChunk] = Field(default_factory=list)
    notes: list[ChatSourceNote] = Field(default_factory=list)


class ChatMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: int
    session_id: int
    role: str
    content: str
    model_used: str | None = None
    tokens_used: int | None = None
    response_time_ms: int | None = None
    sources: ChatSources | None = None
    created_at: datetime
    updated_at: datetime


class ChatResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: str | None = None
    description: str | None = None
    is_archived: bool
    is_pinned: bool
    last_message_at: datetime
    created_at: datetime
    updated_at: datetime
    messages: list[ChatMessageResponse] = Field(default_factory=list)
