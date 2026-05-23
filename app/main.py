"""FastAPI backend for the RAG chatbot."""

import os
from pathlib import Path
from typing import AsyncGenerator

import anthropic
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .document_processor import process_document
from .vector_store import add_document, delete_document, list_documents, query

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MODEL = "claude-opus-4-8"
MAX_CONTEXT_CHUNKS = 6

app = FastAPI(title="Consultant RAG Chatbot")

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ── Models ────────────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    document_filter: str | None = None  # restrict retrieval to one document


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_system_prompt(context_chunks: list[dict]) -> str:
    if not context_chunks:
        return (
            "You are a helpful consultant assistant. "
            "No documents have been uploaded yet. Ask the user to upload documents first."
        )

    context_text = "\n\n---\n\n".join(
        f"[Source: {c['source']}]\n{c['text']}" for c in context_chunks
    )
    return (
        "You are an expert consultant assistant. Answer questions accurately and concisely "
        "based ONLY on the document context provided below. "
        "If the answer is not in the context, say so clearly.\n\n"
        f"<context>\n{context_text}\n</context>"
    )


async def _stream_response(
    messages: list[ChatMessage],
    document_filter: str | None,
) -> AsyncGenerator[str, None]:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Use the last user message for retrieval
    last_user_msg = next(
        (m.content for m in reversed(messages) if m.role == "user"), ""
    )
    chunks = query(last_user_msg, n_results=MAX_CONTEXT_CHUNKS, source_filter=document_filter)
    system_prompt = _build_system_prompt(chunks)

    api_messages = [{"role": m.role, "content": m.content} for m in messages]

    with client.messages.stream(
        model=MODEL,
        max_tokens=2048,
        system=system_prompt,
        messages=api_messages,
    ) as stream:
        for text in stream.text_stream:
            yield text


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    index = STATIC_DIR / "index.html"
    return HTMLResponse(content=index.read_text(encoding="utf-8"))


@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    allowed = {".pdf", ".docx", ".xlsx", ".txt", ".md"}
    ext = Path(file.filename).suffix.lower()
    if ext not in allowed:
        raise HTTPException(400, f"Unsupported file type '{ext}'. Allowed: {', '.join(allowed)}")

    file_bytes = await file.read()
    if len(file_bytes) > 50 * 1024 * 1024:  # 50 MB limit
        raise HTTPException(400, "File too large (max 50 MB).")

    try:
        chunks = process_document(file.filename, file_bytes)
    except ValueError as e:
        raise HTTPException(400, str(e))

    num_chunks = add_document(file.filename, chunks)
    return {"filename": file.filename, "chunks_indexed": num_chunks}


@app.get("/documents")
async def get_documents():
    return {"documents": list_documents()}


@app.delete("/documents/{filename}")
async def remove_document(filename: str):
    removed = delete_document(filename)
    if removed == 0:
        raise HTTPException(404, f"Document '{filename}' not found.")
    return {"filename": filename, "chunks_removed": removed}


@app.post("/chat")
async def chat(request: ChatRequest):
    if not ANTHROPIC_API_KEY:
        raise HTTPException(500, "ANTHROPIC_API_KEY is not set.")
    if not request.messages:
        raise HTTPException(400, "No messages provided.")

    return StreamingResponse(
        _stream_response(request.messages, request.document_filter),
        media_type="text/plain",
    )
