"""FastAPI application factory — registers routers, middleware, and startup lifecycle."""

import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from .auth.routes import router as auth_router
from .chat.routes import router as chat_router
from .config import settings
from .core.limiter import limiter
from .core.logging import setup_logging
from .documents.routes import router as documents_router
from .projects.routes import router as projects_router
from .vector_store.store import init_model

setup_logging()

STATIC_DIR   = Path(__file__).parent / "static"
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
    logger.info("Starting '{}' — loading embedding model ({})…", app.title, settings.embed_model)
    await init_model()
    logger.info("Ready. model={} demo_mode={}", settings.openai_model, not bool(settings.openai_api_key))
    yield
    logger.info("Shutting down.")


# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(title="Consultant RAG Chatbot", version="1.0.0", lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.opt(exception=exc).error("Unhandled error — {} {}", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected error occurred. Please try again."},
    )


# ── Routers ────────────────────────────────────────────────────────────────────

app.include_router(auth_router)
app.include_router(projects_router)
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
