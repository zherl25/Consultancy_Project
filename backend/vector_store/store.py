"""Async SQLite vector store — sentence-transformers embeddings, numpy cosine similarity."""

import asyncio
from datetime import datetime, timezone
from typing import Any

import aiosqlite
import numpy as np
from loguru import logger
from sentence_transformers import SentenceTransformer

from ..config import settings
from ..db import DB_PATH

_model: SentenceTransformer | None = None

# ── Schema ─────────────────────────────────────────────────────────────────────

_SQL_CHUNKS = """
CREATE TABLE IF NOT EXISTS chunks (
    id          TEXT PRIMARY KEY,
    source      TEXT    NOT NULL,
    chunk_index INTEGER NOT NULL,
    text        TEXT    NOT NULL,
    embedding   BLOB    NOT NULL
)"""

_SQL_DOCUMENTS = """
CREATE TABLE IF NOT EXISTS documents (
    filename    TEXT PRIMARY KEY,
    uploaded_at TEXT    NOT NULL,
    chunk_count INTEGER NOT NULL,
    size_bytes  INTEGER NOT NULL,
    project_id  TEXT    REFERENCES projects(id) ON DELETE SET NULL,
    folder_id   TEXT    REFERENCES project_folders(id) ON DELETE SET NULL
)"""

_SQL_PROJECTS = """
CREATE TABLE IF NOT EXISTS projects (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
)"""

_SQL_FOLDERS = """
CREATE TABLE IF NOT EXISTS project_folders (
    id          TEXT PRIMARY KEY,
    project_id  TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
)"""


async def _init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")
        # Core tables (order matters: projects/folders before documents)
        await db.execute(_SQL_PROJECTS)
        await db.execute(_SQL_FOLDERS)
        await db.execute(_SQL_CHUNKS)
        await db.execute(_SQL_DOCUMENTS)

        # Migrate existing documents table BEFORE creating indexes that depend on new columns
        cursor = await db.execute("PRAGMA table_info(documents)")
        existing_cols = {row[1] for row in await cursor.fetchall()}
        if "project_id" not in existing_cols:
            await db.execute(
                "ALTER TABLE documents ADD COLUMN project_id TEXT REFERENCES projects(id) ON DELETE SET NULL"
            )
        if "folder_id" not in existing_cols:
            await db.execute(
                "ALTER TABLE documents ADD COLUMN folder_id TEXT REFERENCES project_folders(id) ON DELETE SET NULL"
            )

        await db.execute("CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks (source)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_docs_project ON documents (project_id)")
        await db.commit()


async def init_model() -> None:
    global _model
    if _model is None:
        logger.info("Loading embedding model: {}", settings.embed_model)
        _model = await asyncio.to_thread(SentenceTransformer, settings.embed_model)
    await _init_db()


def _get_model() -> SentenceTransformer:
    if _model is None:
        raise RuntimeError("Embedding model not initialised — call init_model() at startup.")
    return _model


def _cosine_scores(query_vec: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    q     = query_vec / (np.linalg.norm(query_vec) + 1e-10)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-10
    return (matrix / norms) @ q


# ── Document operations ────────────────────────────────────────────────────────

async def add_document(
    filename: str,
    chunks: list[str],
    *,
    size_bytes: int = 0,
    project_id: str | None = None,
    folder_id: str | None = None,
) -> int:
    model: SentenceTransformer = _get_model()
    embeddings: np.ndarray = await asyncio.to_thread(
        model.encode, chunks, show_progress_bar=False, normalize_embeddings=False
    )

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("DELETE FROM chunks WHERE source = ?", (filename,))
        await db.executemany(
            "INSERT INTO chunks (id, source, chunk_index, text, embedding) VALUES (?, ?, ?, ?, ?)",
            [
                (f"{filename}::{i}", filename, i, text, embeddings[i].astype(np.float32).tobytes())
                for i, text in enumerate(chunks)
            ],
        )
        await db.execute(
            """INSERT OR REPLACE INTO documents
               (filename, uploaded_at, chunk_count, size_bytes, project_id, folder_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (filename, datetime.now(timezone.utc).isoformat(), len(chunks), size_bytes,
             project_id, folder_id),
        )
        await db.commit()

    return len(chunks)


async def list_documents(
    project_id: str | None = None,
    folder_id: str | None = None,
) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        if folder_id:
            cursor = await db.execute(
                """SELECT filename, uploaded_at, chunk_count, size_bytes, project_id, folder_id
                   FROM documents WHERE folder_id = ? ORDER BY filename""",
                (folder_id,),
            )
        elif project_id:
            cursor = await db.execute(
                """SELECT filename, uploaded_at, chunk_count, size_bytes, project_id, folder_id
                   FROM documents WHERE project_id = ? ORDER BY filename""",
                (project_id,),
            )
        else:
            cursor = await db.execute(
                """SELECT filename, uploaded_at, chunk_count, size_bytes, project_id, folder_id
                   FROM documents ORDER BY filename"""
            )
        rows = await cursor.fetchall()

    return [
        {
            "filename":    r[0],
            "uploaded_at": r[1],
            "chunk_count": r[2],
            "size_bytes":  r[3],
            "project_id":  r[4],
            "folder_id":   r[5],
        }
        for r in rows
    ]


async def delete_document(filename: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        cursor = await db.execute("SELECT COUNT(*) FROM chunks WHERE source = ?", (filename,))
        count: int = (await cursor.fetchone())[0]
        if count == 0:
            return 0
        await db.execute("DELETE FROM chunks WHERE source = ?", (filename,))
        await db.execute("DELETE FROM documents WHERE filename = ?", (filename,))
        await db.commit()
    return count


async def delete_project_documents(project_id: str) -> int:
    """Delete all chunks + document records belonging to a project."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute(
            "DELETE FROM chunks WHERE source IN (SELECT filename FROM documents WHERE project_id = ?)",
            (project_id,),
        )
        cursor = await db.execute("DELETE FROM documents WHERE project_id = ?", (project_id,))
        count = cursor.rowcount
        await db.commit()
    return count


async def delete_folder_documents(folder_id: str) -> int:
    """Delete all chunks + document records belonging to a folder."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute(
            "DELETE FROM chunks WHERE source IN (SELECT filename FROM documents WHERE folder_id = ?)",
            (folder_id,),
        )
        cursor = await db.execute("DELETE FROM documents WHERE folder_id = ?", (folder_id,))
        count = cursor.rowcount
        await db.commit()
    return count


# ── Query ──────────────────────────────────────────────────────────────────────

async def query(
    text: str,
    n_results: int = 5,
    project_id: str | None = None,
    source_filter: str | None = None,
) -> list[dict[str, Any]]:
    model     = _get_model()
    query_vec = (await asyncio.to_thread(model.encode, [text], show_progress_bar=False))[0]

    async with aiosqlite.connect(DB_PATH) as db:
        if source_filter:
            cursor = await db.execute(
                "SELECT c.source, c.text, c.embedding FROM chunks c WHERE c.source = ?",
                (source_filter,),
            )
        elif project_id:
            cursor = await db.execute(
                """SELECT c.source, c.text, c.embedding
                   FROM chunks c
                   JOIN documents d ON c.source = d.filename
                   WHERE d.project_id = ?""",
                (project_id,),
            )
        else:
            cursor = await db.execute("SELECT source, text, embedding FROM chunks")
        rows = await cursor.fetchall()

    if not rows:
        return []

    sources    = [r[0] for r in rows]
    texts      = [r[1] for r in rows]
    embeddings = np.array([np.frombuffer(r[2], dtype=np.float32) for r in rows])

    scores = _cosine_scores(query_vec, embeddings)
    ranked = sorted(zip(scores, range(len(rows))), reverse=True)[:n_results]

    return [
        {"text": texts[idx], "source": sources[idx], "score": float(score)}
        for score, idx in ranked
    ]
