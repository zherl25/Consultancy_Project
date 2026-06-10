"""Async SQLite vector store — sentence-transformers embeddings, numpy cosine similarity."""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite
import numpy as np
from loguru import logger
from sentence_transformers import SentenceTransformer

from ..config import settings

DB_PATH = Path(__file__).parent.parent.parent / "data" / "store.db"

_model: SentenceTransformer | None = None

_SQL_CREATE_CHUNKS = """
CREATE TABLE IF NOT EXISTS chunks (
    id          TEXT PRIMARY KEY,
    source      TEXT    NOT NULL,
    chunk_index INTEGER NOT NULL,
    text        TEXT    NOT NULL,
    embedding   BLOB    NOT NULL
)
"""
_SQL_CREATE_DOCUMENTS = """
CREATE TABLE IF NOT EXISTS documents (
    filename    TEXT PRIMARY KEY,
    uploaded_at TEXT    NOT NULL,
    chunk_count INTEGER NOT NULL,
    size_bytes  INTEGER NOT NULL
)
"""
_SQL_CREATE_IDX = "CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks (source)"


async def _init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute(_SQL_CREATE_CHUNKS)
        await db.execute(_SQL_CREATE_DOCUMENTS)
        await db.execute(_SQL_CREATE_IDX)
        await db.commit()


async def init_model() -> None:
    """Load the embedding model and initialise the database schema."""
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


async def add_document(filename: str, chunks: list[str], *, size_bytes: int = 0) -> int:
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
            """INSERT OR REPLACE INTO documents (filename, uploaded_at, chunk_count, size_bytes)
               VALUES (?, ?, ?, ?)""",
            (filename, datetime.now(timezone.utc).isoformat(), len(chunks), size_bytes),
        )
        await db.commit()

    return len(chunks)


async def query(
    text: str, n_results: int = 5, source_filter: str | None = None
) -> list[dict[str, Any]]:
    model     = _get_model()
    query_vec = (await asyncio.to_thread(model.encode, [text], show_progress_bar=False))[0]

    async with aiosqlite.connect(DB_PATH) as db:
        if source_filter:
            cursor = await db.execute(
                "SELECT source, text, embedding FROM chunks WHERE source = ?", (source_filter,)
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


async def list_documents() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT filename, uploaded_at, chunk_count, size_bytes FROM documents ORDER BY filename"
        )
        rows = await cursor.fetchall()
    return [
        {"filename": r[0], "uploaded_at": r[1], "chunk_count": r[2], "size_bytes": r[3]}
        for r in rows
    ]


async def delete_document(filename: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        cursor = await db.execute(
            "SELECT COUNT(*) FROM chunks WHERE source = ?", (filename,)
        )
        count: int = (await cursor.fetchone())[0]
        if count == 0:
            return 0
        await db.execute("DELETE FROM chunks WHERE source = ?", (filename,))
        await db.execute("DELETE FROM documents WHERE filename = ?", (filename,))
        await db.commit()
    return count
