"""FastAPI backend for the Consultant RAG Chatbot."""

import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import openai
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from .config import settings
from .document_processor import process_document
from .vector_store import add_document, delete_document, init_model, list_documents, query

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
log = logging.getLogger(__name__)

STATIC_DIR   = Path(__file__).parent / "static"
# When running behind nginx (Docker), set SERVE_STATIC=false so FastAPI skips
# static-file serving and lets nginx handle it. Defaults to true for local dev.
SERVE_STATIC = os.getenv("SERVE_STATIC", "true").lower() == "true"


# ── Middleware ─────────────────────────────────────────────────────────────────

class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a short request ID to every request for log correlation."""

    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())[:8]
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


# ── Lifespan ───────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting up '%s' — loading embedding model (%s)…", app.title, settings.embed_model)
    init_model()
    log.info(
        "Ready. model=%s demo_mode=%s",
        settings.openai_model,
        not bool(settings.openai_api_key),
    )
    yield
    log.info("Shutting down.")


# ── App factory ────────────────────────────────────────────────────────────────

app = FastAPI(title="Consultant RAG Chatbot", version="1.0.0", lifespan=lifespan)

app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

if SERVE_STATIC and STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ── Global exception handler ───────────────────────────────────────────────────

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    log.error("Unhandled error — %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected error occurred. Please try again."},
    )


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
            "source":  c["source"],
            "score":   round(c["score"] * 100),
            "preview": c["text"][:220].replace("\n", " "),
        }
        for c in chunks
    ]


def _build_system_prompt(chunks: list[dict]) -> str:
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
            "No documents have been uploaded. Use the Documents page to upload a PDF, DOCX, "
            "XLSX, or TXT file, then ask questions about it."
        )
    else:
        sources_str = ", ".join(sorted({c["source"] for c in chunks}))
        preview     = chunks[0]["text"][:280].replace("\n", " ")
        body = (
            f"**Demo mode** — no API key is configured yet.\n\n"
            f"Your question: *\"{user_msg}\"*\n\n"
            f"The retrieval system found **{len(chunks)} relevant passage(s)** "
            f"from: `{sources_str}`\n\n"
            f"**Top passage:**\n> {preview}…\n\n"
            f"---\n"
            f"Add your `OPENAI_API_KEY` to `.env` and restart the server to get real GPT-4o answers."
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

    api_messages = [{"role": "system", "content": _build_system_prompt(chunks)}] + [
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
    except openai.APIError as exc:
        log.error("OpenAI API error: %s", exc)
        yield _sse({"type": "error", "message": f"OpenAI error: {exc}"})


async def _stream_response(
    messages: list[ChatMessage], document_filter: str | None
) -> AsyncGenerator[str, None]:
    user_msg = next((m.content for m in reversed(messages) if m.role == "user"), "")
    chunks   = query(user_msg, n_results=settings.max_context_chunks, source_filter=document_filter)

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
        "status":    "ok",
        "model":     settings.openai_model,
        "demo_mode": not bool(settings.openai_api_key),
    }


if SERVE_STATIC:
    @app.get("/", response_class=HTMLResponse)
    async def root():
        return HTMLResponse(content=(STATIC_DIR / "index.html").read_text(encoding="utf-8"))


@app.post("/upload")
async def upload_document(request: Request, file: UploadFile = File(...)):
    allowed = {".pdf", ".docx", ".xlsx", ".txt", ".md"}
    suffix  = Path(file.filename).suffix.lower()

    if suffix not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {', '.join(sorted(allowed))}",
        )

    file_bytes = await file.read()
    max_bytes  = settings.upload_max_mb * 1024 * 1024

    if len(file_bytes) > max_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"File exceeds the {settings.upload_max_mb} MB limit.",
        )

    try:
        chunks = process_document(file.filename, file_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    num_chunks = add_document(file.filename, chunks, size_bytes=len(file_bytes))
    log.info(
        "Indexed '%s': %d chunks  [%s]",
        file.filename,
        num_chunks,
        getattr(request.state, "request_id", "-"),
    )
    return {"filename": file.filename, "chunks_indexed": num_chunks, "size_bytes": len(file_bytes)}


@app.get("/documents")
async def get_documents():
    return {"documents": list_documents()}


@app.delete("/documents/{filename:path}")
async def remove_document(filename: str, request: Request):
    removed = delete_document(filename)
    if removed == 0:
        raise HTTPException(status_code=404, detail=f"Document '{filename}' not found.")

    log.info(
        "Deleted '%s': %d chunks removed  [%s]",
        filename,
        removed,
        getattr(request.state, "request_id", "-"),
    )
    return {"filename": filename, "chunks_removed": removed}


@app.post("/chat")
async def chat(request_body: ChatRequest):
    if not request_body.messages:
        raise HTTPException(status_code=400, detail="No messages provided.")

    return StreamingResponse(
        _stream_response(request_body.messages, request_body.document_filter),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
