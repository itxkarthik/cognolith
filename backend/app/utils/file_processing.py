from pathlib import Path

from fastapi import HTTPException
from pypdf import PdfReader
from docx import Document as DocxDocument


def extract_text_from_file(file_path: str) -> str:
	suffix = Path(file_path).suffix.lower()

	if suffix == ".pdf":
		return _extract_pdf_text(file_path)
	if suffix == ".docx":
		return _extract_docx_text(file_path)
	if suffix == ".md":
		return _extract_markdown_text(file_path)
	if suffix == ".txt":
		return _extract_plain_text(file_path)

	raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")


def _extract_pdf_text(file_path: str) -> str:
	try:
		reader = PdfReader(file_path)
		parts: list[str] = []
		for page in reader.pages:
			parts.append(page.extract_text() or "")
		return "\n".join(parts)
	except Exception as exc:
		raise HTTPException(status_code=400, detail=f"Failed to read PDF: {exc}")


def _extract_docx_text(file_path: str) -> str:
	try:
		doc = DocxDocument(file_path)
		return "\n".join(paragraph.text for paragraph in doc.paragraphs)
	except Exception as exc:
		raise HTTPException(status_code=400, detail=f"Failed to read DOCX: {exc}")


def _extract_markdown_text(file_path: str) -> str:
	return _extract_plain_text(file_path)


def _extract_plain_text(file_path: str) -> str:
	try:
		with open(file_path, "r", encoding="utf-8", errors="replace") as file:
			return file.read()
	except Exception as exc:
		raise HTTPException(status_code=400, detail=f"Failed to read text file: {exc}")
