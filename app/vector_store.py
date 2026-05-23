"""ChromaDB vector store with sentence-transformers embeddings."""

import hashlib
from pathlib import Path
from typing import List, Dict, Any

import chromadb
from chromadb.utils import embedding_functions

CHROMA_PATH = Path(__file__).parent.parent / "chroma_db"
COLLECTION_NAME = "consultant_docs"
EMBED_MODEL = "all-MiniLM-L6-v2"  # fast, good quality, 384-dim

_client: chromadb.PersistentClient | None = None
_collection = None


def _get_collection():
    global _client, _collection
    if _collection is None:
        _client = chromadb.PersistentClient(path=str(CHROMA_PATH))
        ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=EMBED_MODEL
        )
        _collection = _client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def _chunk_id(filename: str, index: int) -> str:
    key = f"{filename}::{index}"
    return hashlib.md5(key.encode()).hexdigest()


def add_document(filename: str, chunks: List[str]) -> int:
    """Store document chunks in the vector store. Returns number of chunks added."""
    collection = _get_collection()

    ids = [_chunk_id(filename, i) for i in range(len(chunks))]
    metadatas = [{"source": filename, "chunk_index": i} for i in range(len(chunks))]

    # Upsert so re-uploading the same file refreshes it
    collection.upsert(documents=chunks, ids=ids, metadatas=metadatas)
    return len(chunks)


def query(text: str, n_results: int = 5, source_filter: str | None = None) -> List[Dict[str, Any]]:
    """Return the top-n most relevant chunks for a query."""
    collection = _get_collection()

    where = {"source": source_filter} if source_filter else None
    results = collection.query(
        query_texts=[text],
        n_results=min(n_results, collection.count() or 1),
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    hits = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        hits.append({"text": doc, "source": meta["source"], "score": 1 - dist})
    return hits


def list_documents() -> List[str]:
    """Return unique document names stored in the collection."""
    collection = _get_collection()
    if collection.count() == 0:
        return []
    results = collection.get(include=["metadatas"])
    sources = {m["source"] for m in results["metadatas"]}
    return sorted(sources)


def delete_document(filename: str) -> int:
    """Delete all chunks belonging to a document. Returns number of chunks removed."""
    collection = _get_collection()
    results = collection.get(where={"source": filename}, include=["metadatas"])
    ids = results["ids"]
    if ids:
        collection.delete(ids=ids)
    return len(ids)
