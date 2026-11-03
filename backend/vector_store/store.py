"""Async SQLite vector store — sentence-transformers embeddings, numpy cosine similarity."""

import asyncio
import re
import uuid
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
    embedding   BLOB    NOT NULL,
    doc_id      TEXT
)"""

# Documents are identified by id, not filename — the same filename can exist
# in several folders/projects (e.g. every client has a "Quality Manual.docx").
_SQL_DOCUMENTS = """
CREATE TABLE IF NOT EXISTS {table} (
    id          TEXT PRIMARY KEY,
    filename    TEXT    NOT NULL,
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
        await db.execute(_SQL_DOCUMENTS.format(table="documents"))

        # Migrate existing tables BEFORE creating indexes that depend on new columns
        cursor = await db.execute("PRAGMA table_info(documents)")
        doc_cols = {row[1] for row in await cursor.fetchall()}
        if "id" not in doc_cols:
            await _migrate_documents_to_ids(db, doc_cols)

        cursor = await db.execute("PRAGMA table_info(chunks)")
        if "doc_id" not in {row[1] for row in await cursor.fetchall()}:
            await db.execute("ALTER TABLE chunks ADD COLUMN doc_id TEXT")
            await db.execute(
                "UPDATE chunks SET doc_id = (SELECT d.id FROM documents d WHERE d.filename = chunks.source)"
            )

        await db.execute("CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks (source)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks (doc_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_docs_project ON documents (project_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_docs_folder_file ON documents (folder_id, filename)")
        await _init_keyword_index(db)
        await db.commit()


async def _init_keyword_index(db: aiosqlite.Connection) -> None:
    """BM25 keyword index over chunk text, kept in sync with `chunks` by triggers.

    Keyed by chunk id rather than rowid: `chunks` has a TEXT primary key, so its
    implicit rowids are not stable across VACUUM.
    """
    cursor = await db.execute("SELECT 1 FROM sqlite_master WHERE name = 'chunks_fts'")
    is_new = await cursor.fetchone() is None
    await db.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts "
        "USING fts5(chunk_id UNINDEXED, text, tokenize = 'porter unicode61')"
    )
    await db.execute(
        """CREATE TRIGGER IF NOT EXISTS chunks_fts_ai AFTER INSERT ON chunks BEGIN
               INSERT INTO chunks_fts (chunk_id, text) VALUES (new.id, new.text);
           END"""
    )
    await db.execute(
        """CREATE TRIGGER IF NOT EXISTS chunks_fts_ad AFTER DELETE ON chunks BEGIN
               DELETE FROM chunks_fts WHERE chunk_id = old.id;
           END"""
    )
    if is_new:
        logger.info("Building keyword index for existing chunks")
        await db.execute("INSERT INTO chunks_fts (chunk_id, text) SELECT id, text FROM chunks")


async def _migrate_documents_to_ids(db: aiosqlite.Connection, cols: set[str]) -> None:
    """Rebuild the legacy filename-keyed documents table with a surrogate id primary key."""
    logger.info("Migrating documents table to id-based keys")
    project_col = "project_id" if "project_id" in cols else "NULL"
    folder_col  = "folder_id" if "folder_id" in cols else "NULL"
    await db.execute(_SQL_DOCUMENTS.format(table="documents_new"))
    await db.execute(
        f"""INSERT INTO documents_new
            (id, filename, uploaded_at, chunk_count, size_bytes, project_id, folder_id)
            SELECT lower(hex(randomblob(16))), filename, uploaded_at, chunk_count, size_bytes,
                   {project_col}, {folder_col}
            FROM documents"""
    )
    await db.execute("DROP TABLE documents")
    await db.execute("ALTER TABLE documents_new RENAME TO documents")


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
) -> tuple[str, int]:
    """Index a document. Re-uploading the same filename into the same folder replaces it.

    Returns (doc_id, chunk_count).
    """
    model: SentenceTransformer = _get_model()
    embeddings: np.ndarray = await asyncio.to_thread(
        model.encode, chunks, show_progress_bar=False, normalize_embeddings=False
    )

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        # `IS` matches NULL too, so un-foldered uploads are also replaced in place
        cursor = await db.execute(
            "SELECT id FROM documents WHERE filename = ? AND folder_id IS ? AND project_id IS ?",
            (filename, folder_id, project_id),
        )
        existing = await cursor.fetchone()
        doc_id = existing[0] if existing else uuid.uuid4().hex

        await db.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
        await db.executemany(
            "INSERT INTO chunks (id, doc_id, source, chunk_index, text, embedding) VALUES (?, ?, ?, ?, ?, ?)",
            [
                (f"{doc_id}::{i}", doc_id, filename, i, text, embeddings[i].astype(np.float32).tobytes())
                for i, text in enumerate(chunks)
            ],
        )
        await db.execute(
            """INSERT OR REPLACE INTO documents
               (id, filename, uploaded_at, chunk_count, size_bytes, project_id, folder_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (doc_id, filename, datetime.now(timezone.utc).isoformat(), len(chunks), size_bytes,
             project_id, folder_id),
        )
        await db.commit()

    return doc_id, len(chunks)


_DOC_COLUMNS = "id, filename, uploaded_at, chunk_count, size_bytes, project_id, folder_id"


def _doc_row(r) -> dict:
    return {
        "id":          r[0],
        "filename":    r[1],
        "uploaded_at": r[2],
        "chunk_count": r[3],
        "size_bytes":  r[4],
        "project_id":  r[5],
        "folder_id":   r[6],
    }


async def list_documents(
    project_id: str | None = None,
    folder_id: str | None = None,
) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        if folder_id:
            cursor = await db.execute(
                f"SELECT {_DOC_COLUMNS} FROM documents WHERE folder_id = ? ORDER BY filename",
                (folder_id,),
            )
        elif project_id:
            cursor = await db.execute(
                f"SELECT {_DOC_COLUMNS} FROM documents WHERE project_id = ? ORDER BY filename",
                (project_id,),
            )
        else:
            cursor = await db.execute(f"SELECT {_DOC_COLUMNS} FROM documents ORDER BY filename")
        rows = await cursor.fetchall()

    return [_doc_row(r) for r in rows]


async def delete_document(doc_id: str) -> tuple[str, int] | None:
    """Delete a document and its chunks. Returns (filename, chunks_removed), or None if not found."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        cursor = await db.execute("SELECT filename FROM documents WHERE id = ?", (doc_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        cursor = await db.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
        count = cursor.rowcount
        await db.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        await db.commit()
    return row[0], count


async def delete_project_documents(project_id: str) -> int:
    """Delete all chunks + document records belonging to a project."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute(
            "DELETE FROM chunks WHERE doc_id IN (SELECT id FROM documents WHERE project_id = ?)",
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
            "DELETE FROM chunks WHERE doc_id IN (SELECT id FROM documents WHERE folder_id = ?)",
            (folder_id,),
        )
        cursor = await db.execute("DELETE FROM documents WHERE folder_id = ?", (folder_id,))
        count = cursor.rowcount
        await db.commit()
    return count


# ── Query ──────────────────────────────────────────────────────────────────────

_QUERY_SELECT = """SELECT c.id, c.source, c.text, c.embedding, p.name
                   FROM chunks c
                   LEFT JOIN documents d ON c.doc_id = d.id
                   LEFT JOIN projects  p ON p.id = d.project_id"""

_RRF_K          = 60   # standard reciprocal-rank-fusion constant
_KEYWORD_LIMIT  = 50   # keyword candidates considered per search
_STOPWORDS = frozenset(
    "a an and are as at be by can did do does for from has have how i in is it its me my "
    "of on or our please show tell that the their them there these they this to was we "
    "were what when where which who whom why will with you your about any all give list".split()
)
_TERM_RE = re.compile(r"\w[\w.\-/]*\w|\w")


def _fts_query(queries: list[str]) -> str | None:
    """Build an FTS5 OR-query from the meaningful terms. Each term is quoted, so codes
    like "8.5.1" or "NC-01" match as exact token sequences."""
    terms: list[str] = []
    for q in queries:
        for term in _TERM_RE.findall(q.lower()):
            term = term.strip(".-/")
            if term and term not in _STOPWORDS and (len(term) > 1 or term.isdigit()) and term not in terms:
                terms.append(term)
    if not terms:
        return None
    return " OR ".join('"' + t.replace('"', '""') + '"' for t in terms[:24])


async def query(
    text: str | list[str],
    n_results: int = 5,
    project_id: str | None = None,
    source_filter: str | None = None,
) -> list[dict[str, Any]]:
    """Hybrid search: semantic (embeddings) + keyword (BM25), merged with reciprocal
    rank fusion. With several query texts, each chunk's semantic score is its best
    match across them. The returned `score` is the cosine similarity, for display."""
    queries    = [text] if isinstance(text, str) else text
    model      = _get_model()
    query_vecs = await asyncio.to_thread(model.encode, queries, show_progress_bar=False)

    if source_filter:
        where, params = " WHERE c.source = ?", (source_filter,)
    elif project_id:
        where, params = " WHERE d.project_id = ?", (project_id,)
    else:
        where, params = "", ()

    fts = _fts_query(queries)
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(_QUERY_SELECT + where, params)
        rows = await cursor.fetchall()
        keyword_ids: list[str] = []
        if fts and rows:
            cursor = await db.execute(
                f"""SELECT f.chunk_id FROM chunks_fts f
                    JOIN chunks c ON c.id = f.chunk_id
                    LEFT JOIN documents d ON c.doc_id = d.id
                    WHERE chunks_fts MATCH ?{where.replace(' WHERE', ' AND')}
                    ORDER BY bm25(chunks_fts) LIMIT {_KEYWORD_LIMIT}""",
                (fts, *params),
            )
            keyword_ids = [r[0] for r in await cursor.fetchall()]

    if not rows:
        return []

    embeddings = np.array([np.frombuffer(r[3], dtype=np.float32) for r in rows])
    cosine     = np.max([_cosine_scores(q, embeddings) for q in query_vecs], axis=0)

    fused = np.zeros(len(rows))
    for rank, idx in enumerate(np.argsort(-cosine)):
        fused[idx] += 1.0 / (_RRF_K + rank + 1)
    index_of = {r[0]: i for i, r in enumerate(rows)}
    for rank, chunk_id in enumerate(keyword_ids):
        if chunk_id in index_of:
            fused[index_of[chunk_id]] += 1.0 / (_RRF_K + rank + 1)

    ranked = np.argsort(-fused)[:n_results]
    return [
        {"text": rows[i][2], "source": rows[i][1], "project": rows[i][4], "score": float(cosine[i])}
        for i in ranked
    ]
