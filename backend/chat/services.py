"""Chat response streaming: RAG retrieval + OpenAI / demo."""

import asyncio
import json
from typing import AsyncGenerator

import openai
from loguru import logger

from ..config import settings
from ..vector_store.store import query
from .models import ChatMessage


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


async def _demo_stream(user_msg: str, chunks: list[dict]) -> AsyncGenerator[str, None]:
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
    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)

    api_messages = [{"role": "system", "content": _build_system_prompt(chunks)}] + [
        {"role": m.role, "content": m.content} for m in messages
    ]

    try:
        stream = await client.chat.completions.create(
            model=settings.openai_model,
            max_tokens=settings.max_tokens,
            messages=api_messages,
            stream=True,
        )
        async for chunk in stream:
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
        logger.error("OpenAI API error: {}", exc)
        yield _sse({"type": "error", "message": f"OpenAI error: {exc}"})


async def stream_response(
    messages: list[ChatMessage], document_filter: str | None
) -> AsyncGenerator[str, None]:
    user_msg = next((m.content for m in reversed(messages) if m.role == "user"), "")
    chunks   = await query(user_msg, n_results=settings.max_context_chunks, source_filter=document_filter)

    if not settings.openai_api_key:
        async for event in _demo_stream(user_msg, chunks):
            yield event
    else:
        async for event in _openai_stream(messages, chunks):
            yield event
