import logging
from pathlib import Path

from docx import Document as DocxDocument
from fastapi import HTTPException
from pypdf import PdfReader

logger = logging.getLogger(__name__)


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
    except Exception:
        logger.exception("Failed to parse PDF", extra={"file_path": file_path})
        raise HTTPException(status_code=400, detail="Failed to read PDF file")


def _extract_docx_text(file_path: str) -> str:
    try:
        doc = DocxDocument(file_path)
        return "\n".join(paragraph.text for paragraph in doc.paragraphs)
    except Exception:
        logger.exception("Failed to parse DOCX", extra={"file_path": file_path})
        raise HTTPException(status_code=400, detail="Failed to read DOCX file")


def _extract_markdown_text(file_path: str) -> str:
    return _extract_plain_text(file_path)


def _extract_plain_text(file_path: str) -> str:
    try:
        with open(file_path, encoding="utf-8", errors="replace") as file:
            return file.read()
    except Exception:
        logger.exception("Failed to parse text file", extra={"file_path": file_path})
        raise HTTPException(status_code=400, detail="Failed to read text file")
