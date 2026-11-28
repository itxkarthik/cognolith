from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from fastapi import HTTPException, UploadFile

from app.core.config import settings
from app.services.document_service import _save_upload
from app.utils.file_validation import validate_upload_file


@pytest.mark.asyncio
async def test_streamed_upload_stops_at_size_limit_and_removes_partial_file(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(settings, "MAX_FILE_SIZE", 32)
    upload = UploadFile(filename="large.txt", file=BytesIO(b"x" * 64))

    with pytest.raises(HTTPException) as exc_info:
        _save_upload(upload)

    assert exc_info.value.status_code == 413
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_docx_zip_bomb_is_rejected_before_extraction() -> None:
    archive = BytesIO()
    with ZipFile(archive, "w", ZIP_DEFLATED) as docx:
        docx.writestr("[Content_Types].xml", "<Types />")
        docx.writestr("word/document.xml", "A" * 1_000_000)
    archive.seek(0)
    upload = UploadFile(filename="hostile.docx", file=archive)

    with pytest.raises(HTTPException, match="compressed DOCX"):
        await validate_upload_file(upload)
