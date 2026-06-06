"""FastAPI application factory — registers routers, middleware, and startup lifecycle."""

import logging
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from .config import settings
from .chat.routes import router as chat_router
from .documents.routes import router as documents_router
from .vector_store.store import init_model

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
log = logging.getLogger(__name__)

STATIC_DIR   = Path(__file__).parent / "static"
# Set SERVE_STATIC=false when running behind nginx (Docker); defaults true for local dev.
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
    log.info("Starting '%s' — loading embedding model (%s)…", app.title, settings.embed_model)
    init_model()
    log.info(
        "Ready. model=%s demo_mode=%s",
        settings.openai_model,
        not bool(settings.openai_api_key),
    )
    yield
    log.info("Shutting down.")


# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(title="Consultant RAG Chatbot", version="1.0.0", lifespan=lifespan)

app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    log.error("Unhandled error — %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected error occurred. Please try again."},
    )


# ── Routers ────────────────────────────────────────────────────────────────────

app.include_router(documents_router)
app.include_router(chat_router)


# ── Static files & SPA root (local dev only) ──────────────────────────────────

if SERVE_STATIC and STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

if SERVE_STATIC:
    @app.get("/", response_class=HTMLResponse)
    async def root():
        return HTMLResponse(content=(STATIC_DIR / "index.html").read_text(encoding="utf-8"))


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status":    "ok",
        "model":     settings.openai_model,
        "demo_mode": not bool(settings.openai_api_key),
    }
