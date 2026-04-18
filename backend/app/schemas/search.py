from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.utils.sanitization import sanitize_plain_text


class SearchFilters(BaseModel):
    entity_types: list[Literal["document", "note", "chat"]] | None = None
    tags: list[str] | None = None
    folder_id: int | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None

    @field_validator("tags", mode="before")
    @classmethod
    def sanitize_tags(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        return [sanitize_plain_text(tag) for tag in value]


class SearchQuery(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    filters: SearchFilters | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    @field_validator("query", mode="before")
    @classmethod
    def sanitize_query(cls, value: str) -> str:
        return sanitize_plain_text(value)


class SearchResultItem(BaseModel):
    id: int
    entity_type: Literal["document", "note", "chat"]
    title: str | None = None
    snippet: str | None = None
    score: float | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultItem]
    total: int
    page: int
    page_size: int
    filters: SearchFilters | None = None
