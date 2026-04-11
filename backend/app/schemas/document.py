from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils.sanitization import sanitize_plain_text


class DocumentCreate(BaseModel):
	title: str = Field(min_length=1, max_length=255)
	tags: list[str] = Field(default_factory=list)
	language: str = Field(default="en", max_length=10)

	@field_validator("title", mode="before")
	@classmethod
	def sanitize_title(cls, value: str) -> str:
		return sanitize_plain_text(value)

	@field_validator("tags", mode="before")
	@classmethod
	def sanitize_tags(cls, value: list[str]) -> list[str]:
		return [sanitize_plain_text(tag) for tag in value]


class DocumentUpdate(BaseModel):
	title: str | None = Field(default=None, min_length=1, max_length=255)
	summary: str | None = None
	tags: list[str] | None = None
	keywords: list[str] | None = None
	language: str | None = Field(default=None, max_length=10)

	@field_validator("title", mode="before")
	@classmethod
	def sanitize_title(cls, value: str | None) -> str | None:
		if value is None:
			return value
		return sanitize_plain_text(value)

	@field_validator("summary", mode="before")
	@classmethod
	def sanitize_summary(cls, value: str | None) -> str | None:
		if value is None:
			return value
		return sanitize_plain_text(value)

	@field_validator("tags", mode="before")
	@classmethod
	def sanitize_tags(cls, value: list[str] | None) -> list[str] | None:
		if value is None:
			return value
		return [sanitize_plain_text(tag) for tag in value]

	@field_validator("keywords", mode="before")
	@classmethod
	def sanitize_keywords(cls, value: list[str] | None) -> list[str] | None:
		if value is None:
			return value
		return [sanitize_plain_text(keyword) for keyword in value]


class DocumentResponse(BaseModel):
	model_config = ConfigDict(from_attributes=True)

	id: int
	user_id: int
	title: str
	file_name: str
	# file_path intentionally excluded - internal server path, not for client exposure
	file_size: int
	file_type: str
	mime_type: str
	status: str
	language: str
	tags: list[str]
	keywords: list[str]
	summary: str | None = None
	content_preview: str | None = None
	chunk_count: int
	word_count: int | None = None
	page_count: int | None = None
	processing_error: str | None = None
	is_deleted: bool
	created_at: datetime
	updated_at: datetime


class DocumentContentResponse(BaseModel):
	model_config = ConfigDict(from_attributes=True)

	id: int
	title: str
	status: str
	content: str
	updated_at: datetime


class DocumentList(BaseModel):
	data: list[DocumentResponse]
	count: int
