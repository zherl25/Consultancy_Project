# ════════════════════════════════════════════════════════════
#  Consultant AI — Production Dockerfile
#  Build context must be the project root (handled by docker-compose.yml).
# ════════════════════════════════════════════════════════════

FROM python:3.12-slim

# ── Python runtime flags ──────────────────────────────────
# PYTHONDONTWRITEBYTECODE : suppress .pyc files in the image
# PYTHONUNBUFFERED        : flush logs immediately (no buffering)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# ── System packages ───────────────────────────────────────
# python:3.12-slim ships without curl; we use Python's urllib for the
# health-check so we don't need to add any extra OS packages here.
# PyMuPDF ≥1.24 ships bundled MuPDF wheels — no libmupdf required.

# ── Python dependencies ───────────────────────────────────
# Copy requirements first so this expensive layer is cached unless
# requirements.txt changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Embedding model pre-download ──────────────────────────
# Download 'all-MiniLM-L6-v2' into the image at build time so the
# container never needs to reach HuggingFace at runtime.
# NOTE: HF_HUB_OFFLINE must NOT be set here so the download can proceed.
ENV SENTENCE_TRANSFORMERS_HOME=/app/.cache/models
RUN python -c "\
from sentence_transformers import SentenceTransformer; \
SentenceTransformer('all-MiniLM-L6-v2'); \
print('Model cached successfully.')"

# ── Application source ────────────────────────────────────
# Copy after the model layer so a code change doesn't invalidate the
# (slow) pip-install and model-download layers above.
COPY . .

# ── Runtime environment ───────────────────────────────────
# Block all HuggingFace network calls — the model is already on disk.
ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

# ── Networking ────────────────────────────────────────────
EXPOSE 8000

# ── Health check ──────────────────────────────────────────
# start_period gives the embedding model time to load on first boot.
HEALTHCHECK \
  --interval=30s \
  --timeout=10s \
  --start-period=90s \
  --retries=3 \
  CMD python -c "\
import urllib.request, sys; \
urllib.request.urlopen('http://localhost:8000/health'); \
sys.exit(0)" || exit 1

# ── Entrypoint ────────────────────────────────────────────
# Use uvicorn directly (no --reload in production).
CMD ["python", "-m", "uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1"]
