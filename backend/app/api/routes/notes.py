from typing import Any

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, SessionDep
from app.models.note import Notes
from app.models.user import Message
from app.schemas.note import FolderCreate, NoteCreate, NoteList, NoteResponse, NoteUpdate, TagCreate
from app.services.note_service import (
	create_folder,
	create_note,
	create_tag,
	get_note_by_id,
	list_notes,
	soft_delete_note,
	update_note,
)

router = APIRouter(prefix="/notes", tags=["notes"])


def _to_note_response(note: Notes) -> NoteResponse:
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


@router.post(path="/", response_model=NoteResponse)
def create_note_endpoint(*, session: SessionDep, current_user: CurrentUser, body: NoteCreate) -> Any:
	note = create_note(session=session, current_user=current_user, payload=body)
	return _to_note_response(note)


@router.get(path="/", response_model=NoteList)
def read_notes(
	*,
	session: SessionDep,
	current_user: CurrentUser,
	folder_id: int | None = Query(default=None),
	tag_id: int | None = Query(default=None),
	search: str | None = Query(default=None),
	skip: int = Query(default=0, ge=0),
	limit: int = Query(default=20, ge=1, le=100),
) -> Any:
	notes, total = list_notes(
		session=session,
		current_user=current_user,
		folder_id=folder_id,
		tag_id=tag_id,
		search=search,
		skip=skip,
		limit=limit,
	)
	return NoteList(data=[_to_note_response(note) for note in notes], count=total)


@router.get(path="/{note_id}", response_model=NoteResponse)
def read_note_by_id(*, session: SessionDep, current_user: CurrentUser, note_id: int) -> Any:
	note = get_note_by_id(session=session, current_user=current_user, note_id=note_id)
	return _to_note_response(note)


@router.patch(path="/{note_id}", response_model=NoteResponse)
def update_note_endpoint(*, session: SessionDep, current_user: CurrentUser, note_id: int, body: NoteUpdate) -> Any:
	note = update_note(session=session, current_user=current_user, note_id=note_id, payload=body)
	return _to_note_response(note)


@router.delete(path="/{note_id}", response_model=Message)
def delete_note_endpoint(*, session: SessionDep, current_user: CurrentUser, note_id: int) -> Any:
	soft_delete_note(session=session, current_user=current_user, note_id=note_id)
	return Message(message="Note deleted successfully")


@router.post(path="/folders")
def create_folder_endpoint(*, session: SessionDep, current_user: CurrentUser, body: FolderCreate) -> Any:
	folder = create_folder(session=session, current_user=current_user, payload=body)
	return {
		"id": folder.id,
		"user_id": folder.user_id,
		"name": folder.name,
		"description": folder.description,
		"parent_folder_id": folder.parent_folder_id,
		"color": folder.color,
		"icon": folder.icon,
		"emoji": folder.emoji,
		"created_at": folder.created_at,
		"updated_at": folder.updated_at,
	}


@router.post(path="/tags")
def create_tag_endpoint(*, session: SessionDep, current_user: CurrentUser, body: TagCreate) -> Any:
	tag = create_tag(session=session, current_user=current_user, payload=body)
	return {
		"id": tag.id,
		"user_id": tag.user_id,
		"name": tag.name,
		"color": tag.color,
		"description": tag.description,
		"created_at": tag.created_at,
	}
