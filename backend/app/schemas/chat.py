from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils.sanitization import sanitize_plain_text


class ChatCreate(BaseModel):
	title: str | None = Field(default=None, max_length=255)
	description: str | None = None

	@field_validator("title", "description", mode="before")
	@classmethod
	def sanitize_strings(cls, value: str | None) -> str | None:
		if value is None:
			return value
		return sanitize_plain_text(value)


class ChatMessageCreate(BaseModel):
	content: str = Field(min_length=1)
	role: Literal["user", "assistant", "system"] = "user"

	@field_validator("content", mode="before")
	@classmethod
	def sanitize_content(cls, value: str) -> str:
		return sanitize_plain_text(value)


class ChatMessageResponse(BaseModel):
	model_config = ConfigDict(from_attributes=True)

	id: int
	session_id: int
	role: str
	content: str
	model_used: str | None = None
	tokens_used: int | None = None
	response_time_ms: int | None = None
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
