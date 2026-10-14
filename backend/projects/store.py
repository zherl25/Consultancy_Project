"""Database operations for projects and folders."""

import uuid
from datetime import datetime, timezone

import aiosqlite

from ..db import DB_PATH


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uid() -> str:
    return str(uuid.uuid4())


# ── Projects ───────────────────────────────────────────────────────────────────

async def create_project(name: str, description: str) -> dict:
    row = {"id": _uid(), "name": name, "description": description,
           "created_at": _now(), "updated_at": _now()}
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute(
            "INSERT INTO projects (id, name, description, created_at, updated_at) VALUES (?,?,?,?,?)",
            (row["id"], row["name"], row["description"], row["created_at"], row["updated_at"]),
        )
        await db.commit()
    return row


async def list_projects() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """SELECT p.id, p.name, p.description, p.created_at, p.updated_at,
                      COUNT(d.filename) AS file_count
               FROM projects p
               LEFT JOIN documents d ON d.project_id = p.id
               GROUP BY p.id
               ORDER BY p.created_at DESC"""
        )
        rows = await cursor.fetchall()
    return [
        {"id": r[0], "name": r[1], "description": r[2],
         "created_at": r[3], "updated_at": r[4], "file_count": r[5]}
        for r in rows
    ]


async def get_project(project_id: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id, name, description, created_at, updated_at FROM projects WHERE id = ?",
            (project_id,),
        )
        row = await cursor.fetchone()
    if not row:
        return None
    return {"id": row[0], "name": row[1], "description": row[2],
            "created_at": row[3], "updated_at": row[4]}


async def update_project(project_id: str, name: str | None, description: str | None) -> dict | None:
    existing = await get_project(project_id)
    if not existing:
        return None
    new_name = name if name is not None else existing["name"]
    new_desc = description if description is not None else existing["description"]
    now = _now()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE projects SET name=?, description=?, updated_at=? WHERE id=?",
            (new_name, new_desc, now, project_id),
        )
        await db.commit()
    return {**existing, "name": new_name, "description": new_desc, "updated_at": now}


async def delete_project(project_id: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        cursor = await db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        await db.commit()
        return cursor.rowcount > 0


# ── Folders ────────────────────────────────────────────────────────────────────

async def create_folder(project_id: str, name: str, sort_order: int = 0) -> dict:
    row = {"id": _uid(), "project_id": project_id, "name": name,
           "sort_order": sort_order, "created_at": _now()}
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute(
            "INSERT INTO project_folders (id, project_id, name, sort_order, created_at) VALUES (?,?,?,?,?)",
            (row["id"], row["project_id"], row["name"], row["sort_order"], row["created_at"]),
        )
        await db.commit()
    return row


async def list_folders(project_id: str) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """SELECT f.id, f.project_id, f.name, f.sort_order, f.created_at
               FROM project_folders f
               WHERE f.project_id = ?
               ORDER BY f.sort_order, f.name""",
            (project_id,),
        )
        folder_rows = await cursor.fetchall()

        folders = []
        for fr in folder_rows:
            dcursor = await db.execute(
                "SELECT id, filename, uploaded_at, chunk_count, size_bytes FROM documents WHERE folder_id = ? ORDER BY filename",
                (fr[0],),
            )
            doc_rows = await dcursor.fetchall()
            folders.append({
                "id": fr[0], "project_id": fr[1], "name": fr[2],
                "sort_order": fr[3], "created_at": fr[4],
                "documents": [
                    {"id": d[0], "filename": d[1], "uploaded_at": d[2], "chunk_count": d[3], "size_bytes": d[4]}
                    for d in doc_rows
                ],
            })
    return folders


async def get_folder(project_id: str, folder_id: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id, project_id, name, sort_order, created_at FROM project_folders WHERE id=? AND project_id=?",
            (folder_id, project_id),
        )
        row = await cursor.fetchone()
    if not row:
        return None
    return {"id": row[0], "project_id": row[1], "name": row[2],
            "sort_order": row[3], "created_at": row[4]}


async def update_folder(project_id: str, folder_id: str, name: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE project_folders SET name=? WHERE id=? AND project_id=?",
            (name, folder_id, project_id),
        )
        await db.commit()
        if cursor.rowcount == 0:
            return None
        cur2 = await db.execute(
            "SELECT id, project_id, name, sort_order, created_at FROM project_folders WHERE id=?",
            (folder_id,),
        )
        row = await cur2.fetchone()
    return {"id": row[0], "project_id": row[1], "name": row[2],
            "sort_order": row[3], "created_at": row[4]}


async def delete_folder(project_id: str, folder_id: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        cursor = await db.execute(
            "DELETE FROM project_folders WHERE id=? AND project_id=?",
            (folder_id, project_id),
        )
        await db.commit()
        return cursor.rowcount > 0
