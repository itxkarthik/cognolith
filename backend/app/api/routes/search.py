from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query
from sqlalchemy import func
from sqlmodel import select

from app.api.deps import CurrentUser, SessionDep
from app.models.chat import ChatMessages, ChatSession
from app.models.document import Document
from app.models.note import Notes
from app.schemas.error import StandardErrorResponse
from app.schemas.search import SearchResponse, SearchResultItem
from app.utils.text_processing import create_content_preview

router = APIRouter(prefix="/search", tags=["search"])


@router.get(
	path="/",
	response_model=SearchResponse,
	responses={
		400: {"model": StandardErrorResponse, "description": "Invalid query parameters"},
		401: {"model": StandardErrorResponse, "description": "Authentication required"},
		500: {"model": StandardErrorResponse, "description": "Internal server error"},
	},
)
def unified_search(
	*,
	session: SessionDep,
	current_user: CurrentUser,
	query: str = Query(min_length=1),
	entity_types: str | None = Query(default=None, description="Comma-separated: document,note,chat"),
	folder_id: int | None = Query(default=None),
	date_from: datetime | None = Query(default=None),
	date_to: datetime | None = Query(default=None),
	page: int = Query(default=1, ge=1),
	page_size: int = Query(default=20, ge=1, le=100),
) -> Any:
	enabled_types = {
		item.strip().lower()
		for item in (entity_types.split(",") if entity_types else ["document", "note", "chat"])
		if item.strip()
	}

	ts_query = func.plainto_tsquery("english", query)
	results: list[SearchResultItem] = []

	if "document" in enabled_types:
		doc_vector = func.to_tsvector(
			"english",
			func.concat(
				func.coalesce(Document.title, ""),
				" ",
				func.coalesce(Document.content, ""),
			),
		)
		doc_score = func.ts_rank(doc_vector, ts_query).label("score")
		doc_statement = select(
			Document.id,
			Document.title,
			Document.content,
			Document.created_at,
			Document.updated_at,
			doc_score,
		).where(
			Document.user_id == current_user.id,
			Document.is_deleted == False,
			doc_vector.op("@@")(ts_query),
		)
		if date_from is not None:
			doc_statement = doc_statement.where(Document.created_at >= date_from)
		if date_to is not None:
			doc_statement = doc_statement.where(Document.created_at <= date_to)
		doc_rows = session.exec(doc_statement.order_by(doc_score.desc()).limit(100)).all()
		for row in doc_rows:
			results.append(
				SearchResultItem(
					id=row.id,
					entity_type="document",
					title=row.title,
					snippet=create_content_preview(row.content or "", max_length=180),
					score=float(row.score or 0),
					created_at=row.created_at,
					updated_at=row.updated_at,
				)
			)

	if "note" in enabled_types:
		note_vector = func.to_tsvector(
			"english",
			func.concat(
				func.coalesce(Notes.title, ""),
				" ",
				func.coalesce(Notes.content, ""),
			),
		)
		note_score = func.ts_rank(note_vector, ts_query).label("score")
		note_statement = select(
			Notes.id,
			Notes.title,
			Notes.content,
			Notes.created_at,
			Notes.updated_at,
			note_score,
		).where(
			Notes.user_id == current_user.id,
			Notes.is_deleted == False,
			note_vector.op("@@")(ts_query),
		)
		if folder_id is not None:
			note_statement = note_statement.where(Notes.folder_id == folder_id)
		if date_from is not None:
			note_statement = note_statement.where(Notes.created_at >= date_from)
		if date_to is not None:
			note_statement = note_statement.where(Notes.created_at <= date_to)
		note_rows = session.exec(note_statement.order_by(note_score.desc()).limit(100)).all()
		for row in note_rows:
			results.append(
				SearchResultItem(
					id=row.id,
					entity_type="note",
					title=row.title,
					snippet=create_content_preview(row.content or "", max_length=180),
					score=float(row.score or 0),
					created_at=row.created_at,
					updated_at=row.updated_at,
				)
			)

	if "chat" in enabled_types:
		chat_vector = func.to_tsvector("english", func.coalesce(ChatMessages.content, ""))
		chat_score = func.ts_rank(chat_vector, ts_query).label("score")
		chat_statement = select(
			ChatSession.id.label("session_id"),
			ChatSession.title,
			ChatMessages.content,
			ChatMessages.created_at,
			ChatMessages.updated_at,
			chat_score,
		).join(ChatSession, ChatSession.id == ChatMessages.session_id).where(
			ChatSession.user_id == current_user.id,
			chat_vector.op("@@")(ts_query),
		)
		if date_from is not None:
			chat_statement = chat_statement.where(ChatMessages.created_at >= date_from)
		if date_to is not None:
			chat_statement = chat_statement.where(ChatMessages.created_at <= date_to)
		chat_rows = session.exec(chat_statement.order_by(chat_score.desc()).limit(100)).all()
		for row in chat_rows:
			results.append(
				SearchResultItem(
					id=row.session_id,
					entity_type="chat",
					title=row.title,
					snippet=create_content_preview(row.content or "", max_length=180),
					score=float(row.score or 0),
					created_at=row.created_at,
					updated_at=row.updated_at,
				)
			)

	results.sort(key=lambda item: item.score or 0, reverse=True)
	total = len(results)
	start = (page - 1) * page_size
	paged_results = results[start : start + page_size]

	return SearchResponse(
		query=query,
		results=paged_results,
		total=total,
		page=page,
		page_size=page_size,
		filters=None,
	)
