"""Chat response streaming: agentic RAG with OpenAI tool calling, or a retrieval-only demo."""

import asyncio
import json
from typing import AsyncGenerator

import openai
from loguru import logger

from ..config import settings
from ..projects.store import get_project
from ..vector_store.store import query
from .models import ChatMessage


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


def _sources_payload(chunks: list[dict]) -> list[dict]:
    return [
        {
            "source":  c["source"],
            "project": c.get("project"),
            "score":   round(c["score"] * 100),
            "preview": c["text"][:220].replace("\n", " "),
        }
        for c in chunks
    ]


def _retrieval_queries(user_msgs: list[str]) -> list[str]:
    """Demo mode only (with a key, the model writes its own queries). Search with the
    latest question, plus the latest question joined with the previous one so
    follow-ups like "who owns it?" still find the right passages."""
    if not user_msgs:
        return [""]
    latest = user_msgs[-1]
    if len(user_msgs) == 1:
        return [latest]
    return [latest, f"{user_msgs[-2]}\n{latest}"]


_SYSTEM_PROMPT = (
    "You are Consultant AI, an assistant for an ISO 9001 consultancy. The consultant's client "
    "documents (gap analyses, manuals, procedures, audit reports, management reviews, records, "
    "training) are indexed and reachable only through the search_documents tool.\n\n"
    "- Search by default. Any question the documents could plausibly answer — including short or "
    "general-sounding ones like \"what is the quality objective?\" or questions you suspect the "
    "documents won't cover — must be searched before you answer. Do not ask the user which "
    "project or document they mean before searching; search first, and only ask if the results "
    "are genuinely ambiguous.\n"
    "- Write focused queries with the specific names, clause numbers and codes (e.g. \"NC-01 "
    "torque wrench owner\"), resolving words like \"it\" or \"they\" from the conversation. "
    "Search again with different terms if the first results don't answer the question.\n"
    "- Skip searching only for pure greetings, thanks or small talk, and for questions clearly "
    "about the outside world. You have no internet access, so you cannot give live information "
    "such as weather or news.\n"
    "- Answer document questions only from search results, and name the source document — and "
    "its project when results span several projects. If the results don't contain the answer, "
    "say so plainly; never guess."
)

_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "search_documents",
        "description": (
            "Search the uploaded client documents. Hybrid keyword + semantic search, so include "
            "exact terms like clause numbers, NC/document codes and names. Returns the most "
            "relevant passages with their source file and project."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Focused search query."},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        "strict": True,
    },
}

_MAX_TOOL_ROUNDS = 3


def _format_results(chunks: list[dict]) -> str:
    if not chunks:
        return "No matching passages found."
    return "\n\n---\n\n".join(
        f"[Source: {c['source']}" + (f" | Project: {c['project']}" if c.get("project") else "") + f"]\n{c['text']}"
        for c in chunks
    )


async def _demo_stream(user_msg: str, chunks: list[dict]) -> AsyncGenerator[str, None]:
    if not chunks:
        body = (
            "**Demo mode** — no API key is configured yet.\n\n"
            "No documents have been uploaded. Use the Projects page to upload files, "
            "then ask questions about them."
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
    messages: list[ChatMessage], project_filter: str | None
) -> AsyncGenerator[str, None]:
    """Agentic RAG: the model decides whether and what to search via a tool call.
    Small talk gets no search and no sources; document questions may search several times."""
    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)

    scope = "Searches cover all projects."
    if project_filter:
        project = await get_project(project_filter)
        if project:
            scope = f"The user has selected the project \"{project['name']}\"; searches only cover its documents."

    api_messages: list[dict] = [{"role": "system", "content": f"{_SYSTEM_PROMPT}\n\n{scope}"}] + [
        {"role": m.role, "content": m.content} for m in messages
    ]
    used: dict[tuple[str, str], dict] = {}  # every passage the model saw, deduplicated

    try:
        for round_no in range(_MAX_TOOL_ROUNDS + 1):
            stream = await client.chat.completions.create(
                model=settings.openai_model,
                max_tokens=settings.max_tokens,
                messages=api_messages,
                tools=[_SEARCH_TOOL],
                # last round: force a written answer instead of another search
                tool_choice="none" if round_no == _MAX_TOOL_ROUNDS else "auto",
                stream=True,
            )

            calls: dict[int, dict] = {}
            text = ""
            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta.content:
                    text += delta.content
                    yield _sse({"type": "token", "content": delta.content})
                for tc in delta.tool_calls or []:
                    call = calls.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
                    call["id"] = tc.id or call["id"]
                    if tc.function:
                        call["name"] += tc.function.name or ""
                        call["arguments"] += tc.function.arguments or ""

            if not calls:
                break

            api_messages.append({
                "role": "assistant",
                "content": text or None,
                "tool_calls": [
                    {"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": c["arguments"]}}
                    for c in calls.values()
                ],
            })
            for c in calls.values():
                try:
                    search = json.loads(c["arguments"])["query"]
                except (json.JSONDecodeError, KeyError, TypeError):
                    result = "Invalid tool arguments: expected {\"query\": string}."
                else:
                    logger.info("search_documents query={!r} project={}", search, project_filter or "-")
                    hits = await query(search, n_results=settings.max_context_chunks, project_id=project_filter)
                    for h in hits:
                        used.setdefault((h["source"], h["text"]), h)
                    result = _format_results(hits)
                api_messages.append({"role": "tool", "tool_call_id": c["id"], "content": result})

        sources = sorted(used.values(), key=lambda h: h["score"], reverse=True)
        yield _sse({"type": "sources", "sources": _sources_payload(sources)})
        yield _sse({"type": "done"})

    except openai.AuthenticationError:
        yield _sse({"type": "error", "message": "Invalid API key — check OPENAI_API_KEY in .env."})
    except openai.RateLimitError:
        yield _sse({"type": "error", "message": "Rate limit reached. Please wait a moment and try again."})
    except openai.APIError as exc:
        logger.error("OpenAI API error: {}", exc)
        yield _sse({"type": "error", "message": f"OpenAI error: {exc}"})


async def stream_response(
    messages: list[ChatMessage], project_filter: str | None
) -> AsyncGenerator[str, None]:
    if settings.openai_api_key:
        async for event in _openai_stream(messages, project_filter):
            yield event
        return

    # Demo mode has no model to decide when to search, so search every message
    user_msgs = [m.content for m in messages if m.role == "user"]
    user_msg  = user_msgs[-1] if user_msgs else ""
    chunks    = await query(_retrieval_queries(user_msgs), n_results=settings.max_context_chunks, project_id=project_filter)
    async for event in _demo_stream(user_msg, chunks):
        yield event
