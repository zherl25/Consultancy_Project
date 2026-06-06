"""Document management: upload, list, and delete."""

import asyncio
import logging
from pathlib import Path

from ..config import settings
from ..constants import ALLOWED_SUFFIXES
from ..vector_store import store as vs
from .exceptions import DocumentNotFoundError, FileTooLargeError, UnsupportedFileTypeError
from .models import DeleteResponse, DocumentInfo, DocumentListResponse, UploadResponse
from .processor import process_document

log = logging.getLogger(__name__)


async def upload(filename: str, file_bytes: bytes) -> UploadResponse:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise UnsupportedFileTypeError(
            f"Unsupported file type {suffix!r}. Allowed: {', '.join(sorted(ALLOWED_SUFFIXES))}"
        )

    max_bytes = settings.upload_max_mb * 1024 * 1024
    if len(file_bytes) > max_bytes:
        raise FileTooLargeError(f"File exceeds the {settings.upload_max_mb} MB limit.")

    chunks     = await asyncio.to_thread(process_document, filename, file_bytes)
    num_chunks = await asyncio.to_thread(vs.add_document, filename, chunks, size_bytes=len(file_bytes))
    return UploadResponse(filename=filename, chunks_indexed=num_chunks, size_bytes=len(file_bytes))


async def list_all() -> DocumentListResponse:
    docs = await asyncio.to_thread(vs.list_documents)
    return DocumentListResponse(documents=[DocumentInfo(**doc) for doc in docs])


async def delete(filename: str) -> DeleteResponse:
    removed = await asyncio.to_thread(vs.delete_document, filename)
    if removed == 0:
        raise DocumentNotFoundError(f"Document '{filename}' not found.")
    return DeleteResponse(filename=filename, chunks_removed=removed)
