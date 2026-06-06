"""Document upload, listing, and deletion endpoints."""

import logging

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from . import services
from .exceptions import (
    DocumentNotFoundError,
    DocumentProcessingError,
    FileTooLargeError,
    UnsupportedFileTypeError,
)
from .models import DeleteResponse, DocumentListResponse, UploadResponse

log = logging.getLogger(__name__)

router = APIRouter(tags=["documents"])


@router.post("/upload", response_model=UploadResponse)
async def upload_document(request: Request, file: UploadFile = File(...)):
    file_bytes = await file.read()
    try:
        result = services.upload(file.filename, file_bytes)
    except (UnsupportedFileTypeError, FileTooLargeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except DocumentProcessingError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    log.info(
        "Indexed '%s': %d chunks  [%s]",
        result.filename,
        result.chunks_indexed,
        getattr(request.state, "request_id", "-"),
    )
    return result


@router.get("/documents", response_model=DocumentListResponse)
async def get_documents():
    return services.list_all()


@router.delete("/documents/{filename:path}", response_model=DeleteResponse)
async def remove_document(filename: str, request: Request):
    try:
        result = services.delete(filename)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    log.info(
        "Deleted '%s': %d chunks removed  [%s]",
        result.filename,
        result.chunks_removed,
        getattr(request.state, "request_id", "-"),
    )
    return result
