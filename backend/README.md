# Backend

## Steps to run the backend server:

1. Start ChromaDB (data is always stored under `backend/.chroma_data`):
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

   Pipeline run logs are written to `backend/.logs/pipeline_runs/`.