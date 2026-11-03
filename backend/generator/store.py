"""Questionnaire answers and generated document sets, per client account."""

import json
import uuid
from datetime import datetime, timezone

import aiosqlite

from ..db import DB_PATH

_SQL = [
    """CREATE TABLE IF NOT EXISTS questionnaires (
        user_id    TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        answers    TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS generations (
        id          TEXT PRIMARY KEY,
        user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at  TEXT NOT NULL,
        file_count  INTEGER NOT NULL,
        flag_count  INTEGER NOT NULL,
        summary     TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_generations_user ON generations(user_id, created_at)",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        for sql in _SQL:
            await db.execute(sql)
        await db.commit()


async def get_answers(user_id: str) -> tuple[dict, str | None]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT answers, updated_at FROM questionnaires WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
    return (json.loads(row[0]), row[1]) if row else ({}, None)


async def save_answers(user_id: str, answers: dict) -> str:
    now = _now()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO questionnaires (user_id, answers, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET answers = excluded.answers, updated_at = excluded.updated_at",
            (user_id, json.dumps(answers), now))
        await db.commit()
    return now


async def add_generation(user_id: str, summary: dict, generation_id: str | None = None) -> dict:
    row = {"id": generation_id or uuid.uuid4().hex, "user_id": user_id, "created_at": _now(),
           "file_count": len(summary["files"]), "flag_count": len(summary["flags"]), "summary": summary}
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO generations (id, user_id, created_at, file_count, flag_count, summary) VALUES (?,?,?,?,?,?)",
            (row["id"], user_id, row["created_at"], row["file_count"], row["flag_count"], json.dumps(summary)))
        await db.commit()
    return row


def _gen(r) -> dict:
    return {"id": r[0], "user_id": r[1], "created_at": r[2], "file_count": r[3], "flag_count": r[4],
            "summary": json.loads(r[5])}


async def list_generations(user_id: str) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT id, user_id, created_at, file_count, flag_count, summary FROM generations "
                               "WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
        rows = await cur.fetchall()
    return [_gen(r) for r in rows]


async def get_generation(generation_id: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT id, user_id, created_at, file_count, flag_count, summary FROM generations "
                               "WHERE id = ?", (generation_id,))
        r = await cur.fetchone()
    return _gen(r) if r else None


async def delete_generation(generation_id: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM generations WHERE id = ?", (generation_id,))
        await db.commit()
