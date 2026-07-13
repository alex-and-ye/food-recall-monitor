# Backend

## Setup

Copy `backend/.env.example` to `backend/.env` when you need non-default configuration. Environment variables can also be set in your shell before starting the server.

## Steps to run the backend server:

1. Start ChromaDB. The data path must match `CHROMA_SERVER_DATA_PATH` (default `backend/.chroma_data`):
   ```bash
   # from repo root
   chroma run --path ./backend/.chroma_data --port 8000

   # or from backend/
   chroma run --path .chroma_data --port 8000
   ```

2. Run the backend server (from repo root or `backend/`):
   ```bash
   # from backend/
   fastapi dev main.py --port 8080

   # from repo root
   fastapi dev backend/main.py --port 8080
   ```

   Pipeline run logs are written to `backend/.logs/pipeline_runs/` by default.

## Ollama

LLM model names and inference options are configured in `config/agents.py`, not via environment variables.
