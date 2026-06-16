"""Project and folder CRUD endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request

from ..auth.services import get_current_user
from ..core.limiter import limiter
from . import services
from .exceptions import FolderNotFoundError, ProjectNotFoundError
from .models import FolderCreate, FolderResponse, FolderUpdate, ProjectCreate, ProjectResponse, ProjectUpdate

router = APIRouter(prefix="/projects", tags=["projects"])


# ── Projects ───────────────────────────────────────────────────────────────────

@router.get("", response_model=list[ProjectResponse])
@limiter.limit("60/minute")
async def list_projects(request: Request, _: str = Depends(get_current_user)):  # noqa: ARG001
    return await services.list_projects()


@router.post("", response_model=ProjectResponse, status_code=201)
@limiter.limit("20/minute")
async def create_project(request: Request, body: ProjectCreate, _: str = Depends(get_current_user)):  # noqa: ARG001
    return await services.create_project(body.name, body.description)


@router.get("/{project_id}", response_model=ProjectResponse)
@limiter.limit("60/minute")
async def get_project(project_id: str, request: Request, _: str = Depends(get_current_user)):  # noqa: ARG001
    try:
        return await services.get_project_detail(project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.patch("/{project_id}", response_model=ProjectResponse)
@limiter.limit("30/minute")
async def update_project(project_id: str, body: ProjectUpdate, request: Request, _: str = Depends(get_current_user)):  # noqa: ARG001
    try:
        return await services.update_project(project_id, body.name, body.description)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.delete("/{project_id}", status_code=200)
@limiter.limit("20/minute")
async def delete_project(project_id: str, request: Request, _: str = Depends(get_current_user)):  # noqa: ARG001
    try:
        await services.delete_project(project_id)
        return {"deleted": True}
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ── Folders ────────────────────────────────────────────────────────────────────

@router.post("/{project_id}/folders", response_model=FolderResponse, status_code=201)
@limiter.limit("30/minute")
async def create_folder(project_id: str, body: FolderCreate, request: Request, _: str = Depends(get_current_user)):  # noqa: ARG001
    try:
        return await services.create_folder(project_id, body.name, body.sort_order)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.patch("/{project_id}/folders/{folder_id}", response_model=FolderResponse)
@limiter.limit("30/minute")
async def update_folder(project_id: str, folder_id: str, body: FolderUpdate, request: Request, _: str = Depends(get_current_user)):  # noqa: ARG001
    if not body.name:
        raise HTTPException(status_code=400, detail="Folder name is required.")
    try:
        return await services.update_folder(project_id, folder_id, body.name)
    except FolderNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.delete("/{project_id}/folders/{folder_id}", status_code=200)
@limiter.limit("20/minute")
async def delete_folder(project_id: str, folder_id: str, request: Request, _: str = Depends(get_current_user)):  # noqa: ARG001
    try:
        await services.delete_folder(project_id, folder_id)
        return {"deleted": True}
    except FolderNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
