from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlmodel import Session, col, or_, select

from app.core.config import settings
from app.models.document import Document, DocumentChunks
from app.models.user import User
from app.schemas.document import DocumentUpdate
from app.utils.file_processing import extract_text_from_file
from app.utils.file_validation import validate_upload_file
from app.utils.text_processing import clean_text, create_content_preview, split_text_into_chunks


async def upload_and_process_document(*, session: Session, current_user: User, file: UploadFile, title: str | None = None, tags: list[str] | None = None, language: str = "en") -> Document:
	await _validate_and_prepare(file)

	saved_path = _save_upload(file)
	file_size = Path(saved_path).stat().st_size

	document = Document(
		user_id=current_user.id,
		title=title or file.filename or "Untitled",
		file_name=file.filename or Path(saved_path).name,
		file_path=saved_path,
		file_size=file_size,
		file_type=Path(saved_path).suffix.lower(),
		mime_type=file.content_type or "application/octet-stream",
		tags=tags or [],
		language=language,
		status="processing",
	)
	session.add(document)
	session.commit()
	session.refresh(document)

	try:
		content = clean_text(extract_text_from_file(saved_path))
		chunks = split_text_into_chunks(content)

		document.content = content
		document.content_preview = create_content_preview(content)
		document.word_count = len(content.split()) if content else 0
		document.chunk_count = len(chunks)
		document.summary = create_content_preview(content, 300) if content else None
		document.status = "completed"

		for index, chunk_content in enumerate(chunks):
			session.add(
				DocumentChunks(
					document_id=document.id,
					chunk_index=index,
					content=chunk_content,
					content_hash=hashlib.sha256(chunk_content.encode("utf-8")).hexdigest(),
					vector_id=f"doc-{document.id}-chunk-{index}",
					token_count=len(chunk_content.split()),
					char_count=len(chunk_content),
				)
			)

		session.add(document)
		session.commit()
		session.refresh(document)
		return document
	except HTTPException:
		document.status = "failed"
		document.processing_error = "Failed to process file"
		session.add(document)
		session.commit()
		raise
	except Exception as exc:
		document.status = "failed"
		document.processing_error = str(exc)
		session.add(document)
		session.commit()
		raise HTTPException(status_code=500, detail=f"Failed to process document: {exc}")


async def _validate_and_prepare(file: UploadFile) -> None:
	await validate_upload_file(file)


def _save_upload(file: UploadFile) -> str:
	upload_dir = Path(settings.UPLOAD_DIR)
	upload_dir.mkdir(parents=True, exist_ok=True)

	ext = Path(file.filename or "").suffix.lower()
	unique_name = f"{uuid.uuid4().hex}{ext}"
	destination = upload_dir / unique_name

	content = file.file.read()
	with open(destination, "wb") as output:
		output.write(content)

	return str(destination)


def list_documents(*, session: Session, current_user: User, search: str | None = None, skip: int = 0, limit: int = 20) -> tuple[list[Document], int]:
	base_statement = select(Document).where(
		Document.user_id == current_user.id,
		Document.is_deleted == False,
	)

	if search:
		like_query = f"%{search}%"
		base_statement = base_statement.where(
			or_(
				col(Document.title).ilike(like_query),
				col(Document.content).ilike(like_query),
			)
		)

	all_documents = session.exec(base_statement.order_by(col(Document.updated_at).desc())).all()
	total = len(all_documents)
	data = all_documents[skip : skip + limit]
	return data, total


def get_document_by_id(*, session: Session, current_user: User, document_id: int) -> Document:
	document = session.exec(
		select(Document).where(
			Document.id == document_id,
			Document.user_id == current_user.id,
			Document.is_deleted == False,
		)
	).first()
	if not document:
		raise HTTPException(status_code=404, detail="Document not found")
	return document


def update_document_metadata(*, session: Session, current_user: User, document_id: int, payload: DocumentUpdate) -> Document:
	document = get_document_by_id(session=session, current_user=current_user, document_id=document_id)

	update_data = payload.model_dump(exclude_unset=True)
	for key, value in update_data.items():
		setattr(document, key, value)

	session.add(document)
	session.commit()
	session.refresh(document)
	return document


def soft_delete_document(*, session: Session, current_user: User, document_id: int) -> None:
	document = get_document_by_id(session=session, current_user=current_user, document_id=document_id)
	document.is_deleted = True
	document.status = "deleted"

	file_path = Path(document.file_path)
	if file_path.exists() and file_path.is_file():
		file_path.unlink(missing_ok=True)

	session.add(document)
	session.commit()
