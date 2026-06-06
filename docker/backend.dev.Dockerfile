###############################
# Dev image — hot reload enabled
# Source code is bind-mounted from the host at runtime (see docker-compose-dev.yaml).
###############################
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SERVE_STATIC=false

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install uv

COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt && \
    rm -rf /root/.cache

# Cache the model outside /app so the bind-mount doesn't shadow it.
# HF_HUB_OFFLINE must NOT be set here so the download can proceed.
ENV SENTENCE_TRANSFORMERS_HOME=/root/.cache/models
RUN python -c "\
from sentence_transformers import SentenceTransformer; \
SentenceTransformer('all-MiniLM-L6-v2'); \
print('Embedding model cached (dev).')"

# Block runtime network calls after model is cached
ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

EXPOSE 8000

# --reload watches for source changes in the bind-mounted volume
CMD ["python", "-m", "uvicorn", "backend.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--reload"]
