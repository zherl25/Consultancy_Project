"""Pure-Python vector store using sentence-transformers + numpy. No C++ required."""

import pickle
from pathlib import Path
from typing import Any

import numpy as np
from sentence_transformers import SentenceTransformer

DB_PATH = Path(__file__).parent.parent / "chroma_db" / "store.pkl"
EMBED_MODEL = "all-MiniLM-L6-v2"

_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBED_MODEL)
    return _model


# Store schema: {"docs": [{"id", "text", "source", "chunk_index"}], "embeddings": np.ndarray}

def _load() -> dict:
    if DB_PATH.exists():
        with open(DB_PATH, "rb") as f:
            return pickle.load(f)
    return {"docs": [], "embeddings": None}


def _save(store: dict) -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DB_PATH, "wb") as f:
        pickle.dump(store, f)


def _cosine_scores(query_vec: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    q = query_vec / (np.linalg.norm(query_vec) + 1e-10)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-10
    return (matrix / norms) @ q


def add_document(filename: str, chunks: list[str]) -> int:
    store = _load()
    model = _get_model()

    # Remove existing chunks for this file (upsert behaviour)
    keep = [d for d in store["docs"] if d["source"] != filename]
    keep_indices = [i for i, d in enumerate(store["docs"]) if d["source"] != filename]

    new_docs = [
        {"id": f"{filename}::{i}", "text": c, "source": filename, "chunk_index": i}
        for i, c in enumerate(chunks)
    ]
    new_embeddings = model.encode(chunks, show_progress_bar=False, normalize_embeddings=False)

    all_docs = keep + new_docs

    if store["embeddings"] is not None and keep_indices:
        kept_embeddings = store["embeddings"][keep_indices]
        all_embeddings = np.vstack([kept_embeddings, new_embeddings])
    else:
        all_embeddings = new_embeddings

    _save({"docs": all_docs, "embeddings": all_embeddings})
    return len(chunks)


def query(text: str, n_results: int = 5, source_filter: str | None = None) -> list[dict[str, Any]]:
    store = _load()
    if not store["docs"] or store["embeddings"] is None:
        return []

    model = _get_model()
    query_vec = model.encode([text], show_progress_bar=False)[0]

    docs = store["docs"]
    embeddings = store["embeddings"]

    if source_filter:
        indices = [i for i, d in enumerate(docs) if d["source"] == source_filter]
        if not indices:
            return []
        sub_emb = embeddings[indices]
        scores = _cosine_scores(query_vec, sub_emb)
        ranked = sorted(zip(scores, indices), reverse=True)[:n_results]
    else:
        scores = _cosine_scores(query_vec, embeddings)
        ranked = sorted(zip(scores, range(len(docs))), reverse=True)[:n_results]

    return [
        {"text": docs[idx]["text"], "source": docs[idx]["source"], "score": float(score)}
        for score, idx in ranked
    ]


def list_documents() -> list[str]:
    store = _load()
    return sorted({d["source"] for d in store["docs"]})


def delete_document(filename: str) -> int:
    store = _load()
    keep_indices = [i for i, d in enumerate(store["docs"]) if d["source"] != filename]
    removed = len(store["docs"]) - len(keep_indices)
    if removed == 0:
        return 0

    new_docs = [store["docs"][i] for i in keep_indices]
    new_embeddings = store["embeddings"][keep_indices] if keep_indices else None

    _save({"docs": new_docs, "embeddings": new_embeddings})
    return removed
