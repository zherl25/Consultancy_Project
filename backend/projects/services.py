"""Project and folder business logic."""

from ..vector_store.store import delete_project_documents, delete_folder_documents
from . import store as db
from .exceptions import FolderNotFoundError, ProjectNotFoundError
from .models import FolderResponse, ProjectResponse

# Default folder structure created for every new project
_ISO_FOLDERS = [
    (0, "01 Gap Analysis"),
    (1, "02 Documentation"),
    (2, "03 Internal Audit"),
    (3, "04 Management Review"),
    (4, "05 Certification Audit"),
    (5, "06 Record"),
    (6, "07 Training"),
]


async def create_project(name: str, description: str = "") -> ProjectResponse:
    project = await db.create_project(name, description)
    for order, folder_name in _ISO_FOLDERS:
        await db.create_folder(project["id"], folder_name, sort_order=order)
    return ProjectResponse(**project, file_count=0, folders=[])


async def list_projects() -> list[ProjectResponse]:
    rows = await db.list_projects()
    return [ProjectResponse(**r, folders=[]) for r in rows]


async def get_project_detail(project_id: str) -> ProjectResponse:
    project = await db.get_project(project_id)
    if not project:
        raise ProjectNotFoundError(f"Project '{project_id}' not found.")
    folders_data = await db.list_folders(project_id)
    file_count = sum(len(f["documents"]) for f in folders_data)
    folders = [FolderResponse(**f) for f in folders_data]
    return ProjectResponse(**project, file_count=file_count, folders=folders)


async def update_project(project_id: str, name: str | None, description: str | None) -> ProjectResponse:
    updated = await db.update_project(project_id, name, description)
    if not updated:
        raise ProjectNotFoundError(f"Project '{project_id}' not found.")
    return ProjectResponse(**updated, file_count=0, folders=[])


async def delete_project(project_id: str) -> None:
    project = await db.get_project(project_id)
    if not project:
        raise ProjectNotFoundError(f"Project '{project_id}' not found.")
    await delete_project_documents(project_id)
    await db.delete_project(project_id)


async def create_folder(project_id: str, name: str, sort_order: int = 99) -> FolderResponse:
    project = await db.get_project(project_id)
    if not project:
        raise ProjectNotFoundError(f"Project '{project_id}' not found.")
    folder = await db.create_folder(project_id, name, sort_order)
    return FolderResponse(**folder)


async def update_folder(project_id: str, folder_id: str, name: str) -> FolderResponse:
    updated = await db.update_folder(project_id, folder_id, name)
    if not updated:
        raise FolderNotFoundError(f"Folder '{folder_id}' not found.")
    return FolderResponse(**updated)


async def delete_folder(project_id: str, folder_id: str) -> None:
    exists = await db.update_folder(project_id, folder_id, "")  # quick existence check
    if exists is None:
        raise FolderNotFoundError(f"Folder '{folder_id}' not found.")
    await delete_folder_documents(folder_id)
    await db.delete_folder(project_id, folder_id)
