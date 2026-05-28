"""FastAPI production backend for the Consultant RAG Chatbot."""

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import openai
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import settings
from .document_processor import process_document
from .vector_store import add_document, delete_document, init_model, list_documents, query

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


# ── Lifespan ───────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Loading embedding model (%s)…", settings.embed_model)
    init_model()
    log.info("Embedding model ready. Demo mode: %s", not bool(settings.openai_api_key))
    yield
    log.info("Shutting down.")


# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(title="Consultant RAG Chatbot", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ── Request / Response models ──────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    document_filter: str | None = None


# ── SSE helpers ────────────────────────────────────────────────────────────────

def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


def _sources_payload(chunks: list[dict]) -> list[dict]:
    return [
        {
            "source": c["source"],
            "score": round(c["score"] * 100),
            "preview": c["text"][:220].replace("\n", " "),
        }
        for c in chunks
    ]


def _build_system(chunks: list[dict]) -> str:
    if not chunks:
        return (
            "You are a helpful consultant assistant. "
            "No relevant context was found in the uploaded documents. "
            "Let the user know politely and suggest they upload relevant documents."
        )
    context = "\n\n---\n\n".join(
        f"[Source: {c['source']}]\n{c['text']}" for c in chunks
    )
    return (
        "You are an expert consultant assistant. "
        "Answer questions accurately and concisely based ONLY on the provided document context. "
        "When referencing specific information, mention the source document. "
        "If the answer cannot be found in the context, say so clearly — do not fabricate.\n\n"
        f"<context>\n{context}\n</context>"
    )


# ── Streaming generators ───────────────────────────────────────────────────────

async def _demo_stream(user_msg: str, chunks: list[dict]) -> AsyncGenerator[str, None]:
    import asyncio

    if not chunks:
        body = (
            "**Demo mode** — no API key is configured yet.\n\n"
            "No documents have been uploaded. Use the sidebar to upload a PDF, DOCX, XLSX, or TXT file, "
            "then ask questions about it."
        )
    else:
        sources_str = ", ".join(sorted({c["source"] for c in chunks}))
        preview = chunks[0]["text"][:280].replace("\n", " ")
        body = (
            f"**Demo mode** — no API key is configured yet.\n\n"
            f"Your question: *\"{user_msg}\"*\n\n"
            f"The retrieval system found **{len(chunks)} relevant passage(s)** "
            f"from: `{sources_str}`\n\n"
            f"**Top passage:**\n> {preview}…\n\n"
            f"---\n"
            f"Add your `OPENAI_API_KEY` to `.env` and restart to get real GPT-4o answers."
        )

    for char in body:
        yield _sse({"type": "token", "content": char})
        await asyncio.sleep(0.007)

    yield _sse({"type": "sources", "sources": _sources_payload(chunks)})
    yield _sse({"type": "done"})


async def _openai_stream(
    messages: list[ChatMessage], chunks: list[dict]
) -> AsyncGenerator[str, None]:
    client = openai.OpenAI(api_key=settings.openai_api_key)
    api_messages = [{"role": "system", "content": _build_system(chunks)}] + [
        {"role": m.role, "content": m.content} for m in messages
    ]

    try:
        stream = client.chat.completions.create(
            model=settings.openai_model,
            max_tokens=settings.max_tokens,
            messages=api_messages,
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield _sse({"type": "token", "content": delta})

        yield _sse({"type": "sources", "sources": _sources_payload(chunks)})
        yield _sse({"type": "done"})

    except openai.AuthenticationError:
        yield _sse({"type": "error", "message": "Invalid API key — check OPENAI_API_KEY in .env."})
    except openai.RateLimitError:
        yield _sse({"type": "error", "message": "Rate limit reached. Please wait a moment and try again."})
    except Exception as exc:
        log.exception("Unexpected OpenAI error")
        yield _sse({"type": "error", "message": f"Unexpected error: {exc}"})


async def _stream_response(
    messages: list[ChatMessage], document_filter: str | None
) -> AsyncGenerator[str, None]:
    user_msg = next((m.content for m in reversed(messages) if m.role == "user"), "")
    chunks = query(user_msg, n_results=settings.max_context_chunks, source_filter=document_filter)

    if not settings.openai_api_key:
        async for event in _demo_stream(user_msg, chunks):
            yield event
    else:
        async for event in _openai_stream(messages, chunks):
            yield event


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "model": settings.openai_model,
        "demo_mode": not bool(settings.openai_api_key),
    }


@app.get("/", response_class=HTMLResponse)
async def root():
    return HTMLResponse(content=(STATIC_DIR / "index.html").read_text(encoding="utf-8"))


@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    allowed = {".pdf", ".docx", ".xlsx", ".txt", ".md"}
    ext = Path(file.filename).suffix.lower()
    if ext not in allowed:
        raise HTTPException(
            400, f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(allowed))}"
        )

    file_bytes = await file.read()
    max_bytes = settings.upload_max_mb * 1024 * 1024
    if len(file_bytes) > max_bytes:
        raise HTTPException(400, f"File exceeds {settings.upload_max_mb} MB limit.")

    try:
        chunks = process_document(file.filename, file_bytes)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    num_chunks = add_document(file.filename, chunks, size_bytes=len(file_bytes))
    log.info("Indexed '%s': %d chunks", file.filename, num_chunks)
    return {"filename": file.filename, "chunks_indexed": num_chunks, "size_bytes": len(file_bytes)}


@app.get("/documents")
async def get_documents():
    return {"documents": list_documents()}


@app.delete("/documents/{filename:path}")
async def remove_document(filename: str):
    removed = delete_document(filename)
    if removed == 0:
        raise HTTPException(404, f"Document '{filename}' not found.")
    log.info("Deleted '%s': %d chunks removed", filename, removed)
    return {"filename": filename, "chunks_removed": removed}


@app.post("/chat")
async def chat(request: ChatRequest):
    if not request.messages:
        raise HTTPException(400, "No messages provided.")
    return StreamingResponse(
        _stream_response(request.messages, request.document_filter),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
