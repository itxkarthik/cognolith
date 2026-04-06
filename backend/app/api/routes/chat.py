from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, SessionDep
from app.models.chat import ChatMessages, ChatSession
from app.schemas.chat import ChatCreate, ChatMessageCreate, ChatMessageResponse, ChatResponse
from app.schemas.note import NoteResponse
from app.services.chat_service import (
	convert_chat_to_note,
	create_chat_session,
	get_chat_session_by_id,
	list_chat_sessions,
	send_message_and_get_response,
)

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatSessionListResponse(BaseModel):
	data: list[ChatResponse]
	count: int


class ConvertChatToNoteRequest(BaseModel):
	title: str | None = Field(default=None, max_length=500)
	folder_id: int | None = None


def _to_chat_message_response(message: ChatMessages) -> ChatMessageResponse:
	return ChatMessageResponse(
		id=message.id,
		session_id=message.session_id,
		role=str(message.role),
		content=message.content,
		model_used=message.model_used,
		tokens_used=message.tokens_used,
		response_time_ms=message.response_time_ms,
		sources=message.sources,
		created_at=message.created_at,
		updated_at=message.updated_at,
	)


def _to_chat_response(chat_session: ChatSession) -> ChatResponse:
	return ChatResponse(
		id=chat_session.id,
		user_id=chat_session.user_id,
		title=chat_session.title,
		description=chat_session.description,
		is_archived=chat_session.is_archived,
		is_pinned=chat_session.is_pinned,
		last_message_at=chat_session.last_message_at,
		created_at=chat_session.created_at,
		updated_at=chat_session.updated_at,
		messages=[_to_chat_message_response(message) for message in chat_session.messages],
	)


def _to_note_response(note: Any) -> NoteResponse:
	return NoteResponse(
		id=note.id,
		user_id=note.user_id,
		folder_id=note.folder_id,
		title=note.title,
		content=note.content,
		content_type=note.content_type,
		summary=note.summary,
		keywords=note.keywords or [],
		tag_ids=[tag.id for tag in note.tags],
		linked_note_ids=[link.target_note_id for link in note.source_links],
		version=note.version,
		is_favorite=note.is_favorite,
		is_archived=note.is_archived,
		is_pinned=note.is_pinned,
		is_deleted=note.is_deleted,
		linked_document_id=note.linked_document_id,
		linked_chat_session_id=note.linked_chat_session_id,
		created_at=note.created_at,
		updated_at=note.updated_at,
	)


@router.post(path="/sessions", response_model=ChatResponse)
def create_chat_session_endpoint(*, session: SessionDep, current_user: CurrentUser, body: ChatCreate) -> Any:
	chat_session = create_chat_session(session=session, current_user=current_user, payload=body)
	return _to_chat_response(chat_session)


@router.get(path="/sessions", response_model=ChatSessionListResponse)
def list_chat_sessions_endpoint(
	*,
	session: SessionDep,
	current_user: CurrentUser,
	skip: int = Query(default=0, ge=0),
	limit: int = Query(default=20, ge=1, le=100),
) -> Any:
	sessions, count = list_chat_sessions(
		session=session,
		current_user=current_user,
		skip=skip,
		limit=limit,
	)
	return ChatSessionListResponse(data=[_to_chat_response(item) for item in sessions], count=count)


@router.get(path="/sessions/{session_id}", response_model=ChatResponse)
def get_chat_session_endpoint(*, session: SessionDep, current_user: CurrentUser, session_id: int) -> Any:
	chat_session = get_chat_session_by_id(
		session=session,
		current_user=current_user,
		chat_session_id=session_id,
	)
	return _to_chat_response(chat_session)


@router.post(path="/sessions/{session_id}/messages", response_model=ChatMessageResponse)
def send_message_endpoint(
	*,
	session: SessionDep,
	current_user: CurrentUser,
	session_id: int,
	body: ChatMessageCreate,
) -> Any:
	_, assistant_message = send_message_and_get_response(
		session=session,
		current_user=current_user,
		chat_session_id=session_id,
		payload=body,
	)
	return _to_chat_message_response(assistant_message)


@router.post(path="/sessions/{session_id}/to-note", response_model=NoteResponse)
def convert_chat_to_note_endpoint(
	*,
	session: SessionDep,
	current_user: CurrentUser,
	session_id: int,
	body: ConvertChatToNoteRequest,
) -> Any:
	note = convert_chat_to_note(
		session=session,
		current_user=current_user,
		chat_session_id=session_id,
		title=body.title,
		folder_id=body.folder_id,
	)
	return _to_note_response(note)
