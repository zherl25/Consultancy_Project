from pydantic import BaseModel


class UploadResponse(BaseModel):
    filename: str
    chunks_indexed: int
    size_bytes: int


class DocumentInfo(BaseModel):
    filename: str
    uploaded_at: str | None
    chunk_count: int
    size_bytes: int


class DocumentListResponse(BaseModel):
    documents: list[DocumentInfo]


class DeleteResponse(BaseModel):
    filename: str
    chunks_removed: int
