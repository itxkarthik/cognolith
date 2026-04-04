from typing import Any

from fastapi import APIRouter, File, Form, Query, UploadFile

from app.api.deps import CurrentUser, SessionDep
from app.models.user import Message
from app.schemas.document import (
	DocumentContentResponse,
	DocumentList,
	DocumentResponse,
	DocumentUpdate,
)
from app.services.document_service import (
	get_document_by_id,
	list_documents,
	soft_delete_document,
	update_document_metadata,
	upload_and_process_document,
)

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post(path="/upload", response_model=DocumentResponse)
async def upload_document(
	*,
	session: SessionDep,
	current_user: CurrentUser,
	file: UploadFile = File(...),
	title: str | None = Form(default=None),
	tags: str | None = Form(default=None),
	language: str = Form(default="en"),
) -> Any:
	parsed_tags = [tag.strip() for tag in tags.split(",") if tag.strip()] if tags else []
	document = await upload_and_process_document(
		session=session,
		current_user=current_user,
		file=file,
		title=title,
		tags=parsed_tags,
		language=language,
	)
	return document


@router.get("", response_model=DocumentList, include_in_schema=False)
@router.get("/", response_model=DocumentList)
def read_documents(
	*,
	session: SessionDep,
	current_user: CurrentUser,
	search: str | None = Query(default=None),
	skip: int = Query(default=0, ge=0),
	limit: int = Query(default=20, ge=1, le=100),
) -> Any:
	documents, total = list_documents(
		session=session,
		current_user=current_user,
		search=search,
		skip=skip,
		limit=limit,
	)
	return DocumentList(data=documents, count=total)


@router.get(path="/{document_id}", response_model=DocumentResponse)
def read_document_by_id(*, session: SessionDep, current_user: CurrentUser, document_id: int) -> Any:
	return get_document_by_id(session=session, current_user=current_user, document_id=document_id)


@router.get(path="/{document_id}/content", response_model=DocumentContentResponse)
def read_document_content(*, session: SessionDep, current_user: CurrentUser, document_id: int) -> Any:
	document = get_document_by_id(session=session, current_user=current_user, document_id=document_id)
	return DocumentContentResponse(
		id=document.id,
		title=document.title,
		status=document.status,
		content=document.content or "",
		updated_at=document.updated_at,
	)


@router.patch(path="/{document_id}", response_model=DocumentResponse)
def update_document(*, session: SessionDep, current_user: CurrentUser, document_id: int, body: DocumentUpdate) -> Any:
	return update_document_metadata(
		session=session,
		current_user=current_user,
		document_id=document_id,
		payload=body,
	)


@router.delete(path="/{document_id}", response_model=Message)
def delete_document(*, session: SessionDep, current_user: CurrentUser, document_id: int) -> Any:
	soft_delete_document(session=session, current_user=current_user, document_id=document_id)
	return Message(message="Document deleted successfully")
