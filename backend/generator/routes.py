"""Documentation generator endpoints.

/generator/*  — client accounts: questionnaire, logo, generate, download
/admin/*      — consultants: see clients and their documents, manage master templates
"""

import asyncio
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from loguru import logger

from ..auth import store as users
from ..auth.services import CurrentUser, require_admin, require_client
from ..core.limiter import limiter
from . import catalog, services, store

router = APIRouter(tags=["generator"])

_LOGO_MAX = 2 * 1024 * 1024
_TEMPLATE_MAX = 20 * 1024 * 1024


# ── Client: questionnaire ──────────────────────────────────────────────────────

@router.get("/generator/questionnaire")
async def get_questionnaire(user: CurrentUser = Depends(require_client)):
    answers, updated_at = await store.get_answers(user.id)
    if not answers:
        answers = services.default_answers()
        account = await users.get_by_id(user.id)
        answers["company_name"] = account["company_name"] if account else ""
    return {"schema": catalog.schema(), "answers": services.normalize_answers(answers),
            "updated_at": updated_at, "has_logo": services.logo_path(user.id) is not None}


@router.put("/generator/questionnaire")
@limiter.limit("60/minute")
async def save_questionnaire(request: Request, body: dict, user: CurrentUser = Depends(require_client)):  # noqa: ARG001
    answers = services.normalize_answers(body)
    updated_at = await store.save_answers(user.id, answers)
    return {"answers": answers, "updated_at": updated_at}


# ── Client: logo ───────────────────────────────────────────────────────────────

@router.put("/generator/logo")
@limiter.limit("20/minute")
async def upload_logo(request: Request, file: UploadFile = File(...),  # noqa: ARG001
                      user: CurrentUser = Depends(require_client)):
    data = await file.read(_LOGO_MAX + 1)
    if len(data) > _LOGO_MAX:
        raise HTTPException(status_code=400, detail="Logo must be 2 MB or smaller.")
    try:
        services.save_logo(user.id, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"has_logo": True}


@router.get("/generator/logo")
async def get_logo(user: CurrentUser = Depends(require_client)):
    path = services.logo_path(user.id)
    if not path:
        raise HTTPException(status_code=404, detail="No logo uploaded.")
    return FileResponse(path)


@router.delete("/generator/logo")
async def delete_logo(user: CurrentUser = Depends(require_client)):
    services.delete_logo(user.id)
    return {"has_logo": False}


# ── Client: generate & download ────────────────────────────────────────────────

def _public(gen: dict) -> dict:
    s = gen["summary"]
    return {"id": gen["id"], "created_at": gen["created_at"], "file_count": gen["file_count"],
            "flag_count": gen["flag_count"], "company_name": s["company_name"], "modules": s["modules"],
            "files": s["files"], "flags": s["flags"]}


@router.post("/generator/generate", status_code=201)
@limiter.limit("10/minute")
async def generate(request: Request, user: CurrentUser = Depends(require_client)):  # noqa: ARG001
    answers, _ = await store.get_answers(user.id)
    if not answers:
        raise HTTPException(status_code=400, detail="Please fill in and save the questionnaire first.")
    generation_id = uuid.uuid4().hex
    try:
        summary = await asyncio.to_thread(services.generate, user.id, generation_id, answers)
    except services.LibraryMissingError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    gen = await store.add_generation(user.id, summary, generation_id)
    logger.info("Generated {} documents for {} ({} flags)", gen["file_count"], user.id, gen["flag_count"])
    return _public(gen)


@router.get("/generator/generations")
async def list_generations(user: CurrentUser = Depends(require_client)):
    return [_public(g) for g in await store.list_generations(user.id)]


async def _owned(generation_id: str, user: CurrentUser) -> dict:
    gen = await store.get_generation(generation_id)
    if not gen or (user.role != "admin" and gen["user_id"] != user.id):
        raise HTTPException(status_code=404, detail="Document set not found.")
    return gen


def _zip_response(gen: dict) -> FileResponse:
    path = services.zip_path(gen["user_id"], gen["id"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="The files for this document set are no longer available.")
    return FileResponse(path, media_type="application/zip", filename=gen["summary"]["zip_name"])


def _file_response(gen: dict, file_path: str) -> FileResponse:
    known = {f["path"] for f in gen["summary"]["files"]}
    if file_path not in known:
        raise HTTPException(status_code=404, detail="File not found.")
    path = services.generation_dir(gen["user_id"], gen["id"]) / file_path
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found.")
    return FileResponse(path, filename=Path(file_path).name)


@router.get("/generator/generations/{generation_id}/download")
async def download_zip(generation_id: str, user: CurrentUser = Depends(require_client)):
    return _zip_response(await _owned(generation_id, user))


@router.get("/generator/generations/{generation_id}/files/{file_path:path}")
async def download_file(generation_id: str, file_path: str, user: CurrentUser = Depends(require_client)):
    return _file_response(await _owned(generation_id, user), file_path)


@router.delete("/generator/generations/{generation_id}")
async def delete_generation(generation_id: str, user: CurrentUser = Depends(require_client)):
    gen = await _owned(generation_id, user)
    services.remove_generation_files(gen["user_id"], gen["id"])
    await store.delete_generation(gen["id"])
    return {"deleted": gen["id"]}


# ── Admin: clients ─────────────────────────────────────────────────────────────

@router.get("/admin/clients")
async def list_clients(_: CurrentUser = Depends(require_admin)):
    out = []
    for c in await users.list_clients():
        answers, updated_at = await store.get_answers(c["id"])
        gens = await store.list_generations(c["id"])
        out.append({"id": c["id"], "email": c["email"], "company_name": c["company_name"],
                    "created_at": c["created_at"], "questionnaire_updated_at": updated_at,
                    "modules": answers.get("modules", []),
                    "generations": [_public(g) for g in gens]})
    return out


@router.get("/admin/generations/{generation_id}/download")
async def admin_download_zip(generation_id: str, user: CurrentUser = Depends(require_admin)):
    return _zip_response(await _owned(generation_id, user))


@router.get("/admin/generations/{generation_id}/files/{file_path:path}")
async def admin_download_file(generation_id: str, file_path: str, user: CurrentUser = Depends(require_admin)):
    return _file_response(await _owned(generation_id, user), file_path)


# ── Admin: master templates ────────────────────────────────────────────────────

def _template(key: str) -> dict:
    try:
        library = services.load_library()
    except services.LibraryMissingError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    entry = next((t for t in library if t["key"] == key), None)
    if not entry:
        raise HTTPException(status_code=404, detail="Template not found.")
    return entry


@router.get("/admin/templates")
async def list_templates(_: CurrentUser = Depends(require_admin)):
    try:
        library = services.load_library()
    except services.LibraryMissingError:
        library = []
    modules = {m["key"]: m["label"] for m in catalog.MODULES} | {"core": "All companies"}
    return [t | {"module_label": modules.get(t["module"], t["module"]),
                 "updated_at": services.master_path(t).stat().st_mtime if services.master_path(t).exists() else None}
            for t in library]


@router.get("/admin/templates/{key}/download")
async def download_template(key: str, _: CurrentUser = Depends(require_admin)):
    entry = _template(key)
    path = services.master_path(entry)
    return FileResponse(path, filename=f"{entry['title']} (master){path.suffix}")


@router.put("/admin/templates/{key}")
@limiter.limit("20/minute")
async def replace_template(request: Request, key: str, file: UploadFile = File(...),  # noqa: ARG001
                           _: CurrentUser = Depends(require_admin)):
    """Replace a master with an edited copy (same file type). The previous version is kept as .bak."""
    entry = _template(key)
    path = services.master_path(entry)
    if Path(file.filename or "").suffix.lower() != path.suffix:
        raise HTTPException(status_code=400, detail=f"Please upload a {path.suffix} file.")
    data = await file.read(_TEMPLATE_MAX + 1)
    if len(data) > _TEMPLATE_MAX or not data.startswith(b"PK"):
        raise HTTPException(status_code=400, detail="That doesn't look like a valid Office file.")
    path.with_suffix(path.suffix + ".bak").write_bytes(path.read_bytes())
    path.write_bytes(data)
    logger.info("Master template '{}' replaced", key)
    return {"key": key, "updated": True}
