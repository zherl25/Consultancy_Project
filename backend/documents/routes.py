"""Document upload, listing, and deletion endpoints."""

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from loguru import logger

from ..auth.services import get_current_user
from ..core.limiter import limiter
from . import services
from .exceptions import (
    DocumentNotFoundError,
    DocumentProcessingError,
    FileTooLargeError,
    UnsupportedFileTypeError,
)
from .models import DeleteResponse, DocumentListResponse, UploadResponse

router = APIRouter(tags=["documents"])


@router.post("/upload", response_model=UploadResponse)
@limiter.limit("20/minute")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    project_id: str | None = Query(default=None),
    folder_id:  str | None = Query(default=None),
    _: str = Depends(get_current_user),
):
    file_bytes = await file.read()
    try:
        result = await services.upload(
            file.filename, file_bytes,
            project_id=project_id,
            folder_id=folder_id,
        )
    except (UnsupportedFileTypeError, FileTooLargeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except DocumentProcessingError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    logger.info(
        "Indexed '{}': {} chunks  project={} folder={}  [{}]",
        result.filename, result.chunks_indexed,
        project_id or "-", folder_id or "-",
        getattr(request.state, "request_id", "-"),
    )
    return result


@router.get("/documents", response_model=DocumentListResponse)
@limiter.limit("60/minute")
async def get_documents(
    request: Request,  # noqa: ARG001
    project_id: str | None = Query(default=None),
    folder_id:  str | None = Query(default=None),
    _: str = Depends(get_current_user),
):
    return await services.list_all(project_id=project_id, folder_id=folder_id)


@router.delete("/documents/{filename:path}", response_model=DeleteResponse)
@limiter.limit("20/minute")
async def remove_document(
    filename: str,
    request: Request,
    _: str = Depends(get_current_user),
):
    try:
        result = await services.delete(filename)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    logger.info(
        "Deleted '{}': {} chunks removed  [{}]",
        result.filename, result.chunks_removed,
        getattr(request.state, "request_id", "-"),
    )
    return result
