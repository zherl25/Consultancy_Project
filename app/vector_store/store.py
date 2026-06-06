"""Pure-Python vector store using sentence-transformers + numpy. No C++ required."""

import pickle
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from sentence_transformers import SentenceTransformer

from ..config import settings

# Resolves to <project_root>/chroma_db/store.pkl in both local and Docker environments.
DB_PATH = Path(__file__).parent.parent.parent / "chroma_db" / "store.pkl"

_model: SentenceTransformer | None = None


def init_model() -> None:
    """Preload the embedding model at startup so the first request is not slow."""
    global _model
    if _model is None:
        _model = SentenceTransformer(settings.embed_model)


def _get_model() -> SentenceTransformer:
    if _model is None:
        init_model()
    return _model


# Store schema:
# {
#   "docs":       [{"id", "text", "source", "chunk_index"}],
#   "embeddings": np.ndarray | None,
#   "metadata":   {filename: {"uploaded_at", "chunk_count", "size_bytes"}}
# }

def _load() -> dict:
    if DB_PATH.exists():
        with open(DB_PATH, "rb") as f:
            data = pickle.load(f)
            if "metadata" not in data:
                data["metadata"] = {}
            return data
    return {"docs": [], "embeddings": None, "metadata": {}}


def _save(store: dict) -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DB_PATH, "wb") as f:
        pickle.dump(store, f)


def _cosine_scores(query_vec: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    q = query_vec / (np.linalg.norm(query_vec) + 1e-10)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-10
    return (matrix / norms) @ q


def add_document(filename: str, chunks: list[str], size_bytes: int = 0) -> int:
    store = _load()
    model = _get_model()

    keep_indices = [i for i, d in enumerate(store["docs"]) if d["source"] != filename]
    keep_docs    = [store["docs"][i] for i in keep_indices]

    new_docs = [
        {"id": f"{filename}::{i}", "text": c, "source": filename, "chunk_index": i}
        for i, c in enumerate(chunks)
    ]
    new_embeddings = model.encode(chunks, show_progress_bar=False, normalize_embeddings=False)

    all_docs = keep_docs + new_docs
    if store["embeddings"] is not None and keep_indices:
        all_embeddings = np.vstack([store["embeddings"][keep_indices], new_embeddings])
    else:
        all_embeddings = np.array(new_embeddings)

    store["metadata"][filename] = {
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "chunk_count": len(chunks),
        "size_bytes":  size_bytes,
    }

    _save({"docs": all_docs, "embeddings": all_embeddings, "metadata": store["metadata"]})
    return len(chunks)


def query(text: str, n_results: int = 5, source_filter: str | None = None) -> list[dict[str, Any]]:
    store = _load()
    if not store["docs"] or store["embeddings"] is None:
        return []

    model     = _get_model()
    query_vec = model.encode([text], show_progress_bar=False)[0]

    docs       = store["docs"]
    embeddings = store["embeddings"]

    if source_filter:
        indices = [i for i, d in enumerate(docs) if d["source"] == source_filter]
        if not indices:
            return []
        scores = _cosine_scores(query_vec, embeddings[indices])
        ranked = sorted(zip(scores, indices), reverse=True)[:n_results]
    else:
        scores = _cosine_scores(query_vec, embeddings)
        ranked = sorted(zip(scores, range(len(docs))), reverse=True)[:n_results]

    return [
        {"text": docs[idx]["text"], "source": docs[idx]["source"], "score": float(score)}
        for score, idx in ranked
    ]


def list_documents() -> list[dict]:
    store   = _load()
    sources = sorted({d["source"] for d in store["docs"]})
    meta    = store.get("metadata", {})
    return [
        {
            "filename":    s,
            "uploaded_at": meta.get(s, {}).get("uploaded_at"),
            "chunk_count": meta.get(s, {}).get("chunk_count", 0),
            "size_bytes":  meta.get(s, {}).get("size_bytes", 0),
        }
        for s in sources
    ]


def delete_document(filename: str) -> int:
    store        = _load()
    keep_indices = [i for i, d in enumerate(store["docs"]) if d["source"] != filename]
    removed      = len(store["docs"]) - len(keep_indices)
    if removed == 0:
        return 0

    new_docs       = [store["docs"][i] for i in keep_indices]
    new_embeddings = store["embeddings"][keep_indices] if keep_indices else None
    store["metadata"].pop(filename, None)

    _save({"docs": new_docs, "embeddings": new_embeddings, "metadata": store["metadata"]})
    return removed
