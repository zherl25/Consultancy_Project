###############################
# Stage 1: Builder
###############################
FROM python:3.12-slim AS builder

RUN pip install uv

WORKDIR /build

# System deps needed only at build time
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc g++ python3-dev ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt && \
    rm -rf /root/.cache

# Pre-download the embedding model so the runtime image is self-contained.
# HF_HUB_OFFLINE must NOT be set here so the download can proceed.
ENV SENTENCE_TRANSFORMERS_HOME=/build/.cache/models
RUN python -c "\
from sentence_transformers import SentenceTransformer; \
SentenceTransformer('all-MiniLM-L6-v2'); \
print('Embedding model cached.')"

###############################
# Stage 2: Runtime
###############################
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Block HuggingFace network calls — model is already on disk
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    SENTENCE_TRANSFORMERS_HOME=/app/.cache/models \
    # nginx owns the frontend in Docker; FastAPI is API-only
    SERVE_STATIC=false

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy pre-downloaded model
COPY --from=builder /build/.cache/models /app/.cache/models

# Copy application source
COPY . .

EXPOSE 8000

# start_period gives the embedding model time to initialise on first boot
HEALTHCHECK \
    --interval=30s \
    --timeout=10s \
    --start-period=90s \
    --retries=3 \
    CMD python -c "\
import urllib.request, sys; \
urllib.request.urlopen('http://localhost:8000/health'); \
sys.exit(0)" || exit 1

CMD ["python", "-m", "uvicorn", "backend.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1"]
