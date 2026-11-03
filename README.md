# Consultant AI

A retrieval-augmented (RAG) chatbot for ISO 9001 consultancy work. Each client is a **project** with the standard ISO folder structure; documents uploaded into a project are parsed, chunked and embedded, and the chat answers questions from those documents with cited sources.

## Features

- **Projects and folders**: every new project gets seven ISO 9001 folders (Gap Analysis, Documentation, Internal Audit, Management Review, Certification Audit, Record, Training). Projects and folders can be renamed, added and deleted.
- **Document ingestion**: PDF, DOCX, XLSX, TXT and Markdown, up to 50 MB per file.
- **Grounded chat**: answers stream over SSE and list the source passages with similarity scores. Retrieval can be scoped to a single project.
- **Chat sessions**: separate chat histories that persist in the browser and can be renamed.
- **Demo mode**: without an OpenAI key, the app still runs retrieval and shows the top passages instead of a generated answer.
- **Documentation generator**: client companies sign up, answer a questionnaire (company details, activities, quality policy and objectives, optional logo) and download a numbered ISO 9001 set (Quality Manual, procedures, forms) built from the consultancy's master templates. Unanswered fields are highlighted in yellow as `[TO BE CONFIRMED: …]` and listed for the client.
- **Auth**: two roles. The consultant admin (credentials from `.env`) uses projects, chat and the Clients page; client companies sign up themselves and only see their questionnaire. JWT bearer tokens and rate limits on every API route.

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
  auth/          JWT login, client sign-up, admin/client role checks
  generator/     questionnaire, template filling (fill.py) and document sets
  chat/          SSE chat streaming (OpenAI or demo)
  documents/     upload, parsing, chunking
  projects/      project and folder CRUD
  vector_store/  embeddings and similarity search
  core/          logging, rate limiter
  static/        SPA (index.html, css, js/pages/*)
docker/          Dockerfiles and nginx config
tools/
  build_templates.py  builds the master template library from a past client's documents
```

### Master templates

The generator fills master templates kept in `data/templates/` (outside git, since they derive from client work). They are built once from an example documentation set:

```bash
python tools/build_templates.py data/templates/build_spec.json
```

The spec names the source files and the client-specific text to turn into fields such as `{{company_name}}`, `{{ref:qp_sales}}` (renumbered document references) and `{{if:design}}` (conditional paragraphs); the token syntax is documented in `backend/generator/fill.py`. Admins can also download a master from the Clients page, edit it in Word or Excel, and upload it back.

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
| POST | `/auth/signup` | Create a client company account |
| GET | `/auth/me` | Validate the current token |
| GET / POST | `/projects` | List or create projects |
| GET / PATCH / DELETE | `/projects/{id}` | Read, update or delete a project |
| POST | `/projects/{id}/folders` | Add a folder |
| PATCH / DELETE | `/projects/{id}/folders/{folder_id}` | Rename or delete a folder |
| POST | `/upload?project_id=&folder_id=` | Upload and index a document |
| GET | `/documents` | List indexed documents |
| DELETE | `/documents/{doc_id}` | Remove a document |
| POST | `/chat` | Stream a chat response (SSE) |
| GET / PUT | `/generator/questionnaire` | Client: read or save questionnaire answers |
| PUT / GET / DELETE | `/generator/logo` | Client: company logo |
| POST | `/generator/generate` | Client: generate a document set |
| GET | `/generator/generations` | Client: list generated sets |
| GET | `/generator/generations/{id}/download` | Client: download a set as zip |
| GET | `/admin/clients` | Admin: clients and their generated sets |
| GET / PUT | `/admin/templates…` | Admin: list, download or replace master templates |
| GET | `/health` | Health check |

## Roadmap

- **Reranking**: re-score retrieved passages with a cross-encoder before answering.
- **Better embeddings**: upgrade from `all-MiniLM-L6-v2` to a stronger embedding model.
