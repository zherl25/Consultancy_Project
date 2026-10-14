from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str
    description: str = ""


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class FolderCreate(BaseModel):
    name: str
    sort_order: int = 0


class FolderUpdate(BaseModel):
    name: str | None = None


class DocumentInfo(BaseModel):
    id: str
    filename: str
    uploaded_at: str | None
    chunk_count: int
    size_bytes: int


class FolderResponse(BaseModel):
    id: str
    project_id: str
    name: str
    sort_order: int
    created_at: str
    documents: list[DocumentInfo] = []


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: str
    created_at: str
    updated_at: str
    file_count: int = 0
    folders: list[FolderResponse] = []
