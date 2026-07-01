import asyncio
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query
from sqlalchemy import func
from sqlalchemy import select as sa_select
from sqlmodel import col, select

from app.ai.embeddings import generate_embedding
from app.ai.rag import ensure_workspace_embeddings
from app.ai.vectorstore import PgVectorStore
from app.api.deps import CurrentUser, SessionDep
from app.models.chat import ChatMessages, ChatSession
from app.models.document import Document
from app.models.note import Notes
from app.schemas.error import StandardErrorResponse
from app.schemas.search import SearchResponse, SearchResultItem
from app.utils.text_processing import create_content_preview

router = APIRouter(prefix="/search", tags=["search"])
logger = logging.getLogger(__name__)


def _merge_result(
    results: dict[tuple[str, int], SearchResultItem], candidate: SearchResultItem
) -> None:
    key = (candidate.entity_type, candidate.id)
    existing = results.get(key)
    if existing is None:
        results[key] = candidate
        return

    if (candidate.score or 0) > (existing.score or 0):
        existing.score = candidate.score
        existing.snippet = candidate.snippet or existing.snippet


@router.get(
    path="",
    response_model=SearchResponse,
    responses={
        400: {
            "model": StandardErrorResponse,
            "description": "Invalid query parameters",
        },
        401: {"model": StandardErrorResponse, "description": "Authentication required"},
        500: {"model": StandardErrorResponse, "description": "Internal server error"},
    },
)
def unified_search(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    query: str = Query(min_length=1),
    entity_types: str
    | None = Query(default=None, description="Comma-separated: document,note,chat"),
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
    results_by_key: dict[tuple[str, int], SearchResultItem] = {}

    if "document" in enabled_types:
        doc_vector = func.to_tsvector(
            "english",
            func.concat(
                func.coalesce(Document.title, ""),
                " ",
                func.coalesce(Document.content, ""),
                " ",
                func.coalesce(Document.summary, ""),
            ),
        )
        doc_score = func.ts_rank(doc_vector, ts_query).label("score")
        doc_statement = sa_select(
            col(Document.id),
            col(Document.title),
            col(Document.content),
            col(Document.created_at),
            col(Document.updated_at),
            doc_score,
        ).where(
            col(Document.user_id) == current_user.id,
            col(Document.is_deleted).is_(False),
            doc_vector.op("@@")(ts_query),
        )
        if date_from is not None:
            doc_statement = doc_statement.where(col(Document.created_at) >= date_from)
        if date_to is not None:
            doc_statement = doc_statement.where(col(Document.created_at) <= date_to)
        doc_rows = (
            session.connection().execute(doc_statement.order_by(doc_score.desc()).limit(100)).all()
        )
        for row in doc_rows:
            _merge_result(
                results_by_key,
                SearchResultItem(
                    id=row.id,
                    entity_type="document",
                    title=row.title,
                    snippet=create_content_preview(row.content or "", max_length=180),
                    score=float(row.score or 0),
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                ),
            )

    if "note" in enabled_types:
        note_vector = func.to_tsvector(
            "english",
            func.concat(
                func.coalesce(Notes.title, ""),
                " ",
                func.coalesce(Notes.content, ""),
                " ",
                func.coalesce(Notes.summary, ""),
            ),
        )
        note_score = func.ts_rank(note_vector, ts_query).label("score")
        note_statement = sa_select(
            col(Notes.id),
            col(Notes.title),
            col(Notes.content),
            col(Notes.created_at),
            col(Notes.updated_at),
            note_score,
        ).where(
            col(Notes.user_id) == current_user.id,
            col(Notes.is_deleted).is_(False),
            note_vector.op("@@")(ts_query),
        )
        if folder_id is not None:
            note_statement = note_statement.where(col(Notes.folder_id) == folder_id)
        if date_from is not None:
            note_statement = note_statement.where(col(Notes.created_at) >= date_from)
        if date_to is not None:
            note_statement = note_statement.where(col(Notes.created_at) <= date_to)
        note_rows = (
            session.connection()
            .execute(note_statement.order_by(note_score.desc()).limit(100))
            .all()
        )
        for row in note_rows:
            _merge_result(
                results_by_key,
                SearchResultItem(
                    id=row.id,
                    entity_type="note",
                    title=row.title,
                    snippet=create_content_preview(row.content or "", max_length=180),
                    score=float(row.score or 0),
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                ),
            )

    if "chat" in enabled_types:
        chat_vector = func.to_tsvector("english", func.coalesce(ChatMessages.content, ""))
        chat_score = func.ts_rank(chat_vector, ts_query).label("score")
        chat_statement = (
            sa_select(
                col(ChatSession.id).label("session_id"),
                col(ChatSession.title),
                col(ChatMessages.content),
                col(ChatMessages.created_at),
                col(ChatMessages.updated_at),
                chat_score,
            )
            .join(ChatSession, col(ChatSession.id) == col(ChatMessages.session_id))
            .where(
                col(ChatSession.user_id) == current_user.id,
                chat_vector.op("@@")(ts_query),
            )
        )
        if date_from is not None:
            chat_statement = chat_statement.where(col(ChatMessages.created_at) >= date_from)
        if date_to is not None:
            chat_statement = chat_statement.where(col(ChatMessages.created_at) <= date_to)
        chat_rows = (
            session.connection()
            .execute(chat_statement.order_by(chat_score.desc()).limit(100))
            .all()
        )
        for row in chat_rows:
            _merge_result(
                results_by_key,
                SearchResultItem(
                    id=row.session_id,
                    entity_type="chat",
                    title=row.title,
                    snippet=create_content_preview(row.content or "", max_length=180),
                    score=float(row.score or 0),
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                ),
            )

    if current_user.id is not None and enabled_types.intersection({"document", "note"}):
        try:
            query_embedding, embedding_model = asyncio.run(
                generate_embedding(
                    session=session,
                    user_id=current_user.id,
                    text=query,
                )
            )
            vector_store = PgVectorStore(session=session)
            vector_store.ensure_schema(embedding_dimensions=len(query_embedding))
            ensure_workspace_embeddings(
                session=session,
                vector_store=vector_store,
                user_id=current_user.id,
                embedding_model=embedding_model,
                include_documents="document" in enabled_types,
                include_notes="note" in enabled_types,
            )
            session.commit()

            if "document" in enabled_types:
                document_hits = vector_store.similarity_search(
                    user_id=current_user.id,
                    query_embedding=query_embedding,
                    top_k=100,
                    similarity_threshold=0.35,
                )
                document_ids = sorted({hit.document_id for hit in document_hits})
                document_statement = select(Document).where(
                    Document.user_id == current_user.id,
                    col(Document.is_deleted).is_(False),
                    col(Document.id).in_(document_ids),
                )
                if date_from is not None:
                    document_statement = document_statement.where(Document.created_at >= date_from)
                if date_to is not None:
                    document_statement = document_statement.where(Document.created_at <= date_to)
                document_map = {
                    document.id: document
                    for document in session.exec(document_statement).all()
                    if document.id is not None
                }
                for hit in document_hits:
                    document = document_map.get(hit.document_id)
                    if document is None:
                        continue
                    _merge_result(
                        results_by_key,
                        SearchResultItem(
                            id=hit.document_id,
                            entity_type="document",
                            title=document.title,
                            snippet=create_content_preview(hit.content, max_length=180),
                            score=float(hit.score),
                            created_at=document.created_at,
                            updated_at=document.updated_at,
                        ),
                    )

            if "note" in enabled_types:
                note_hits = vector_store.note_similarity_search(
                    user_id=current_user.id,
                    query_embedding=query_embedding,
                    top_k=100,
                    similarity_threshold=0.35,
                )
                note_ids = sorted({hit.note_id for hit in note_hits})
                note_statement = select(Notes).where(
                    Notes.user_id == current_user.id,
                    col(Notes.is_deleted).is_not(True),
                    col(Notes.id).in_(note_ids),
                )
                if folder_id is not None:
                    note_statement = note_statement.where(Notes.folder_id == folder_id)
                if date_from is not None:
                    note_statement = note_statement.where(Notes.created_at >= date_from)
                if date_to is not None:
                    note_statement = note_statement.where(Notes.created_at <= date_to)
                note_map = {
                    note.id: note
                    for note in session.exec(note_statement).all()
                    if note.id is not None
                }
                for hit in note_hits:
                    note = note_map.get(hit.note_id)
                    if note is None:
                        continue
                    _merge_result(
                        results_by_key,
                        SearchResultItem(
                            id=hit.note_id,
                            entity_type="note",
                            title=note.title,
                            snippet=create_content_preview(hit.content, max_length=180),
                            score=float(hit.score),
                            created_at=note.created_at,
                            updated_at=note.updated_at,
                        ),
                    )
        except Exception:
            session.rollback()
            logger.warning("Semantic search unavailable; returning lexical results", exc_info=True)

    results = sorted(results_by_key.values(), key=lambda item: item.score or 0, reverse=True)
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
