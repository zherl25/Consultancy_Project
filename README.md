# Consultant RAG Chatbot

A RAG (Retrieval-Augmented Generation) chatbot for consultancy document Q&A, powered by Claude.

## Setup

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Set your API key**
   ```bash
   copy .env.example .env
   # Edit .env and paste your Anthropic API key
   ```

3. **Run**
   ```bash
   python run.py
   ```
   Open http://localhost:8000 in your browser.

## Usage

1. **Upload documents** — drag & drop or click the upload area (PDF, DOCX, XLSX, TXT, MD)
2. **Ask questions** — type in the chat box; the AI retrieves relevant passages and answers
3. **Filter by document** — click a document in the sidebar to restrict Q&A to that file
4. **Delete documents** — click × next to a document to remove it from the knowledge base

## Architecture

```
Browser (HTML/JS)
  ↕ REST + streaming
FastAPI (app/main.py)
  ├── Document upload  →  document_processor.py  →  parse + chunk
  │                       vector_store.py         →  ChromaDB (local)
  └── Chat endpoint    →  query ChromaDB for context
                          Claude API (claude-opus-4-8) streaming response
```

## File structure

```
Consultant_Project/
├── app/
│   ├── main.py               # FastAPI app + endpoints
│   ├── document_processor.py # PDF/DOCX/XLSX/TXT parsing & chunking
│   ├── vector_store.py       # ChromaDB + embeddings
│   └── static/
│       └── index.html        # Web UI
├── chroma_db/                # Vector DB (auto-created)
├── uploads/                  # (optional local copies)
├── requirements.txt
├── run.py
└── .env                      # ANTHROPIC_API_KEY
```
