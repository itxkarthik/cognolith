from typing import Any

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, SessionDep
from app.models.note import Notes
from app.models.user import Message
from app.schemas.error import StandardErrorResponse
from app.schemas.graph import GraphAllResponse, GraphResponse
from app.schemas.note import (
    FolderCreate,
    FolderResponse,
    NoteCreate,
    NoteList,
    NoteResponse,
    NoteUpdate,
    TagCreate,
    TagResponse,
)
from app.services.note_service import (
    create_folder,
    create_note,
    create_tag,
    create_note_link,
    delete_note_link,
    get_full_user_graph,
    get_note_by_id,
    get_note_graph,
    list_folders,
    list_notes,
    list_tags,
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


@router.post(
    path="",
    response_model=NoteResponse,
    responses={
        400: {"model": StandardErrorResponse, "description": "Validation error"},
        401: {"model": StandardErrorResponse, "description": "Authentication required"},
        500: {"model": StandardErrorResponse, "description": "Internal server error"},
    },
)
@router.post(path="/", response_model=NoteResponse, include_in_schema=False)
def create_note_endpoint(
    *, session: SessionDep, current_user: CurrentUser, body: NoteCreate
) -> Any:
    note = create_note(session=session, current_user=current_user, payload=body)
    return _to_note_response(note)


@router.get(
    path="",
    response_model=NoteList,
    responses={
        400: {"model": StandardErrorResponse, "description": "Invalid query parameters"},
        401: {"model": StandardErrorResponse, "description": "Authentication required"},
        500: {"model": StandardErrorResponse, "description": "Internal server error"},
    },
)
@router.get(path="/", response_model=NoteList, include_in_schema=False)
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
    has_more = (skip + limit) < total
    return NoteList(
        data=[_to_note_response(note) for note in notes],
        count=total,
        page_size=limit,
        has_more=has_more,
    )


@router.get(
    path="/folders",
    response_model=list[FolderResponse],
    responses={
        401: {"model": StandardErrorResponse, "description": "Authentication required"},
        500: {"model": StandardErrorResponse, "description": "Internal server error"},
    },
)
def read_folders(*, session: SessionDep, current_user: CurrentUser) -> Any:
    return list_folders(session=session, current_user=current_user)


@router.get(
    path="/tags",
    response_model=list[TagResponse],
    responses={
        401: {"model": StandardErrorResponse, "description": "Authentication required"},
        500: {"model": StandardErrorResponse, "description": "Internal server error"},
    },
)
def read_tags(*, session: SessionDep, current_user: CurrentUser) -> Any:
    return list_tags(session=session, current_user=current_user)


@router.get(
    path="/{note_id}",
    response_model=NoteResponse,
    responses={
        401: {"model": StandardErrorResponse, "description": "Authentication required"},
        403: {"model": StandardErrorResponse, "description": "Access denied"},
        404: {"model": StandardErrorResponse, "description": "Note not found"},
        500: {"model": StandardErrorResponse, "description": "Internal server error"},
    },
)
def read_note_by_id(*, session: SessionDep, current_user: CurrentUser, note_id: int) -> Any:
    note = get_note_by_id(session=session, current_user=current_user, note_id=note_id)
    return _to_note_response(note)


@router.patch(
    path="/{note_id}",
    response_model=NoteResponse,
    responses={
        400: {"model": StandardErrorResponse, "description": "Validation error"},
        401: {"model": StandardErrorResponse, "description": "Authentication required"},
        403: {"model": StandardErrorResponse, "description": "Access denied"},
        404: {"model": StandardErrorResponse, "description": "Note not found"},
        500: {"model": StandardErrorResponse, "description": "Internal server error"},
    },
)
def update_note_endpoint(
    *, session: SessionDep, current_user: CurrentUser, note_id: int, body: NoteUpdate
) -> Any:
    note = update_note(session=session, current_user=current_user, note_id=note_id, payload=body)
    return _to_note_response(note)


@router.delete(
    path="/{note_id}",
    response_model=Message,
    responses={
        401: {"model": StandardErrorResponse, "description": "Authentication required"},
        403: {"model": StandardErrorResponse, "description": "Access denied"},
        404: {"model": StandardErrorResponse, "description": "Note not found"},
        500: {"model": StandardErrorResponse, "description": "Internal server error"},
    },
)
def delete_note_endpoint(*, session: SessionDep, current_user: CurrentUser, note_id: int) -> Any:
    soft_delete_note(session=session, current_user=current_user, note_id=note_id)
    return Message(message="Note deleted successfully")


@router.post(
    path="/folders",
    response_model=FolderResponse,
    responses={
        400: {"model": StandardErrorResponse, "description": "Validation error"},
        401: {"model": StandardErrorResponse, "description": "Authentication required"},
        500: {"model": StandardErrorResponse, "description": "Internal server error"},
    },
)
def create_folder_endpoint(
    *, session: SessionDep, current_user: CurrentUser, body: FolderCreate
) -> Any:
    return create_folder(session=session, current_user=current_user, payload=body)


@router.post(
    path="/tags",
    response_model=TagResponse,
    responses={
        400: {"model": StandardErrorResponse, "description": "Validation error"},
        401: {"model": StandardErrorResponse, "description": "Authentication required"},
        500: {"model": StandardErrorResponse, "description": "Internal server error"},
    },
)
def create_tag_endpoint(*, session: SessionDep, current_user: CurrentUser, body: TagCreate) -> Any:
    return create_tag(session=session, current_user=current_user, payload=body)


# ==================== Knowledge Graph Endpoints ====================


@router.get(
    path="/{note_id}/graph",
    response_model=GraphResponse,
    responses={
        401: {"model": StandardErrorResponse, "description": "Authentication required"},
        403: {"model": StandardErrorResponse, "description": "Access denied"},
        404: {"model": StandardErrorResponse, "description": "Note not found"},
        500: {"model": StandardErrorResponse, "description": "Internal server error"},
    },
)
def get_note_graph_endpoint(
    *, session: SessionDep, current_user: CurrentUser, note_id: int
) -> Any:
    """
    Get knowledge graph for a specific note.
    Returns the note and all directly connected notes (depth=1) with their links.
    """
    nodes, edges = get_note_graph(session=session, current_user=current_user, note_id=note_id)
    
    node_responses = [
        {
            "id": node.id,
            "title": node.title,
            "content_preview": node.content_preview,
            "is_favorite": node.is_favorite,
            "is_archived": node.is_archived,
            "is_pinned": node.is_pinned,
            "color": node.color,
            "emoji": node.emoji,
            "created_at": node.created_at,
            "updated_at": node.updated_at,
        }
        for node in nodes
    ]
    
    edge_responses = [
        {
            "id": edge.id,
            "source_note_id": edge.source_note_id,
            "target_note_id": edge.target_note_id,
            "link_type": edge.link_type,
            "description": edge.description,
            "created_at": edge.created_at,
        }
        for edge in edges
    ]
    
    return GraphResponse(nodes=node_responses, edges=edge_responses, center_node_id=note_id)


@router.get(
    path="/graph/all",
    response_model=GraphAllResponse,
    responses={
        401: {"model": StandardErrorResponse, "description": "Authentication required"},
        500: {"model": StandardErrorResponse, "description": "Internal server error"},
    },
)
def get_full_graph_endpoint(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    limit: int = Query(default=500, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> Any:
    """
    Get full knowledge graph for the user with pagination.
    Returns all notes and their interconnections.
    """
    nodes, edges = get_full_user_graph(
        session=session, current_user=current_user, limit=limit, offset=offset
    )
    
    node_responses = [
        {
            "id": node.id,
            "title": node.title,
            "content_preview": node.content_preview,
            "is_favorite": node.is_favorite,
            "is_archived": node.is_archived,
            "is_pinned": node.is_pinned,
            "color": node.color,
            "emoji": node.emoji,
            "created_at": node.created_at,
            "updated_at": node.updated_at,
        }
        for node in nodes
    ]
    
    edge_responses = [
        {
            "id": edge.id,
            "source_note_id": edge.source_note_id,
            "target_note_id": edge.target_note_id,
            "link_type": edge.link_type,
            "description": edge.description,
            "created_at": edge.created_at,
        }
        for edge in edges
    ]
    
    has_more = len(nodes) == limit
    return GraphAllResponse(nodes=node_responses, edges=edge_responses, has_more=has_more)


@router.post(
    path="/{source_id}/links/{target_id}",
    response_model=Message,
    responses={
        400: {"model": StandardErrorResponse, "description": "Invalid link"},
        401: {"model": StandardErrorResponse, "description": "Authentication required"},
        403: {"model": StandardErrorResponse, "description": "Access denied"},
        404: {"model": StandardErrorResponse, "description": "Note not found"},
        409: {"model": StandardErrorResponse, "description": "Link already exists"},
        500: {"model": StandardErrorResponse, "description": "Internal server error"},
    },
)
def create_link_endpoint(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    source_id: int,
    target_id: int,
    link_type: str = Query(default="related", regex="^(related|referenced|parent|child)$"),
    description: str | None = Query(default=None),
) -> Any:
    """Create a link between two notes."""
    create_note_link(
        session=session,
        current_user=current_user,
        source_note_id=source_id,
        target_note_id=target_id,
        link_type=link_type,
        description=description,
    )
    return Message(message="Link created successfully")


@router.delete(
    path="/{source_id}/links/{target_id}",
    response_model=Message,
    responses={
        401: {"model": StandardErrorResponse, "description": "Authentication required"},
        403: {"model": StandardErrorResponse, "description": "Access denied"},
        404: {"model": StandardErrorResponse, "description": "Link not found"},
        500: {"model": StandardErrorResponse, "description": "Internal server error"},
    },
)
def delete_link_endpoint(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    source_id: int,
    target_id: int,
) -> Any:
    """Delete a link between two notes."""
    delete_note_link(
        session=session,
        current_user=current_user,
        source_note_id=source_id,
        target_note_id=target_id,
    )
    return Message(message="Link deleted successfully")
