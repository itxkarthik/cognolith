from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils.sanitization import sanitize_plain_text


class FolderCreate(BaseModel):
	name: str = Field(min_length=1, max_length=255)
	description: str | None = None
	parent_folder_id: int | None = None
	color: str | None = Field(default=None, max_length=20)
	icon: str | None = Field(default=None, max_length=50)
	emoji: str | None = Field(default=None, max_length=10)

	@field_validator("name", "description", "color", "icon", "emoji", mode="before")
	@classmethod
	def sanitize_strings(cls, value: str | None) -> str | None:
		if value is None:
			return value
		return sanitize_plain_text(value)


class TagCreate(BaseModel):
	name: str = Field(min_length=1, max_length=100)
	color: str | None = Field(default=None, max_length=20)
	description: str | None = None

	@field_validator("name", "color", "description", mode="before")
	@classmethod
	def sanitize_strings(cls, value: str | None) -> str | None:
		if value is None:
			return value
		return sanitize_plain_text(value)


class NoteCreate(BaseModel):
	title: str = Field(min_length=1, max_length=500)
	content: str = Field(min_length=1)
	folder_id: int | None = None
	content_type: str = Field(default="markdown", max_length=20)
	keywords: list[str] = Field(default_factory=list)
	tag_ids: list[int] = Field(default_factory=list)
	linked_note_ids: list[int] = Field(default_factory=list)
	is_favorite: bool = False
	is_pinned: bool = False
	linked_document_id: int | None = None
	linked_chat_session_id: int | None = None

	@field_validator("title", "content", mode="before")
	@classmethod
	def sanitize_required_text(cls, value: str) -> str:
		return sanitize_plain_text(value)

	@field_validator("keywords", mode="before")
	@classmethod
	def sanitize_keywords(cls, value: list[str]) -> list[str]:
		return [sanitize_plain_text(keyword) for keyword in value]


class NoteUpdate(BaseModel):
	title: str | None = Field(default=None, min_length=1, max_length=500)
	content: str | None = Field(default=None, min_length=1)
	folder_id: int | None = None
	content_type: str | None = Field(default=None, max_length=20)
	keywords: list[str] | None = None
	tag_ids: list[int] | None = None
	linked_note_ids: list[int] | None = None
	is_favorite: bool | None = None
	is_archived: bool | None = None
	is_pinned: bool | None = None
	linked_document_id: int | None = None
	linked_chat_session_id: int | None = None

	@field_validator("title", "content", mode="before")
	@classmethod
	def sanitize_optional_text(cls, value: str | None) -> str | None:
		if value is None:
			return value
		return sanitize_plain_text(value)

	@field_validator("keywords", mode="before")
	@classmethod
	def sanitize_keywords(cls, value: list[str] | None) -> list[str] | None:
		if value is None:
			return value
		return [sanitize_plain_text(keyword) for keyword in value]


class NoteResponse(BaseModel):
	model_config = ConfigDict(from_attributes=True)

	id: int
	user_id: int
	folder_id: int | None = None
	title: str
	content: str
	content_type: str
	summary: str | None = None
	keywords: list[str]
	tag_ids: list[int] = Field(default_factory=list)
	linked_note_ids: list[int] = Field(default_factory=list)
	version: int
	is_favorite: bool
	is_archived: bool
	is_pinned: bool
	is_deleted: bool
	linked_document_id: int | None = None
	linked_chat_session_id: int | None = None
	created_at: datetime
	updated_at: datetime


class NoteList(BaseModel):
	data: list[NoteResponse]
	count: int
