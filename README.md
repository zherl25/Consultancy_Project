# Consultant AI

A retrieval-augmented (RAG) chatbot for ISO 9001 consultancy work. Each client is a **project** with the standard ISO folder structure; documents uploaded into a project are parsed, chunked and embedded, and the chat answers questions from those documents with cited sources.

## Features

- **Projects and folders**: every new project gets seven ISO 9001 folders (Gap Analysis, Documentation, Internal Audit, Management Review, Certification Audit, Record, Training). Projects and folders can be renamed, added and deleted.
- **Document ingestion**: PDF, DOCX, XLSX, TXT and Markdown, up to 50 MB per file.
- **Grounded chat**: answers stream over SSE and list the source passages with similarity scores. Retrieval can be scoped to a single project.
- **Chat sessions**: separate chat histories that persist in the browser and can be renamed.
- **Demo mode**: without an OpenAI key, the app still runs retrieval and shows the top passages instead of a generated answer.
- **Auth**: single admin login with JWT bearer tokens, and rate limits on every API route.

## Stack

| Layer | Tech |
|-------|------|
| API | FastAPI, Pydantic Settings, slowapi, python-jose |
| Retrieval | sentence-transformers (`all-MiniLM-L6-v2`), NumPy cosine similarity |
| Storage | SQLite via aiosqlite (WAL mode) |
| LLM | OpenAI (`gpt-4o` by default) |
| Frontend | Vanilla JS ES modules with a hash router; no build step |
| Ops | Docker, docker compose, nginx, loguru JSON logs |

## Project layout

```
backend/
  auth/          JWT login and current-user dependency
  chat/          SSE chat streaming (OpenAI or demo)
  documents/     upload, parsing, chunking
  projects/      project and folder CRUD
  vector_store/  embeddings and similarity search
  core/          logging, rate limiter
  static/        SPA (index.html, css, js/pages/*)
docker/          Dockerfiles and nginx config
```

## Getting started

1. Copy the env file and fill it in:

   ```bash
   cp .env.example .env
   ```

   Set `AUTH_USERNAME`, `AUTH_PASSWORD` and `JWT_SECRET`. `OPENAI_API_KEY` is optional; without it the app runs in demo mode.

2. Run it **locally** (Python 3.12):

   ```bash
   pip install -r requirements.txt
   python run.py
   ```

   Open http://localhost:8000.

   Or run it **with Docker**:

   ```bash
   make dev    # hot reload, bind mounts
   make prod   # production build, detached
   ```

   Run `make help` to list the other targets.

## API

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/auth/login` | Exchange credentials for a JWT |
| GET | `/auth/me` | Validate the current token |
| GET / POST | `/projects` | List or create projects |
| GET / PATCH / DELETE | `/projects/{id}` | Read, update or delete a project |
| POST | `/projects/{id}/folders` | Add a folder |
| PATCH / DELETE | `/projects/{id}/folders/{folder_id}` | Rename or delete a folder |
| POST | `/upload?project_id=&folder_id=` | Upload and index a document |
| GET | `/documents` | List indexed documents |
| DELETE | `/documents/{filename}` | Remove a document |
| POST | `/chat` | Stream a chat response (SSE) |
| GET | `/health` | Health check |

## Roadmap

- **Golden templates**: generate a reusable Word/Excel template set, with placeholders, from existing client projects.
- **Template fill-in**: produce a complete client document package from company details.
