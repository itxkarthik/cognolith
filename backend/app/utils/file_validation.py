import magic
from fastapi import HTTPException, UploadFile

from app.core.config import settings

# Map file extensions to expected MIME types (magic bytes)
EXTENSION_MIME_MAP: dict[str, list[str]] = {
    ".pdf": ["application/pdf"],
    ".docx": [
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",  # .docx is a zip archive
    ],
    ".md": ["text/plain", "text/x-markdown", "text/markdown"],
    ".txt": ["text/plain"],
}


async def validate_upload_file(file: UploadFile) -> None:
    """
    Validate an uploaded file by:
    1. Checking extension is allowed
    2. Checking file size
    3. Validating magic bytes match the declared extension
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    # 1. Extension check
    ext = _get_extension(file.filename)
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' not allowed. Allowed: {settings.ALLOWED_EXTENSIONS}",
        )

    # 2. Read content for size + magic byte checks
    content = await file.read()
    await file.seek(0)  # Reset for downstream consumers

    if len(content) > settings.MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size: {settings.MAX_FILE_SIZE // (1024 * 1024)} MB",
        )

    # 3. Magic bytes validation
    detected_mime = magic.from_buffer(content[:2048], mime=True)
    allowed_mimes = EXTENSION_MIME_MAP.get(ext, [])

    if allowed_mimes and detected_mime not in allowed_mimes:
        raise HTTPException(
            status_code=400,
            detail=f"File content does not match extension '{ext}'. " f"Detected: {detected_mime}",
        )


def _get_extension(filename: str) -> str:
    """Extract the lowercase file extension."""
    dot_index = filename.rfind(".")
    if dot_index == -1:
        return ""
    return filename[dot_index:].lower()
