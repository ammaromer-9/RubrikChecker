from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.config import Settings, get_settings
from app.schemas.files import ExtractedText
from app.services.file_extract import FileExtractionError, extract_text

router = APIRouter(prefix="/files", tags=["files"])


@router.post("/extract", response_model=ExtractedText)
async def extract_file_text(
    file: UploadFile = File(...), settings: Settings = Depends(get_settings)
) -> ExtractedText:
    """Extract text from an uploaded PDF, .docx or .txt file."""
    max_bytes = settings.max_upload_bytes
    # Read one byte past the limit so oversized uploads are rejected without buffering them all.
    content = await file.read(max_bytes + 1)
    try:
        text = extract_text(file.filename or "", content, max_bytes=max_bytes)
    except FileExtractionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ExtractedText(filename=file.filename or "", text=text, char_count=len(text))
