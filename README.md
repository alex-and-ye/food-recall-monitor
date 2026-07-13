# Food Recall Monitor

An AI-powered food safety monitoring platform that uses a locally hosted LLM agent swarm to automatically scrape, translate, classify, and summarize global food recall and foodborne illness reports. Developed in collaboration with the Canadian Food Inspection Agency as an early warning proof-of-concept system.

## Environment variables

The table below lists every environment variable read by the application code.

- **Frontend** variables are loaded automatically by Next.js from `frontend/.env`, `frontend/.env.local`, and related files (see `frontend/.env.example`).

- **Backend** variables are loaded from `backend/.env` (see `backend/.env.example`) and from the process environment; shell values override the `.env` file.

When using Next.js API rewrites, keep `NEXT_PUBLIC_API_URL` and `BACKEND_URL` in sync: the browser should call `/api` on the Next server, and `BACKEND_URL` should point at the FastAPI origin (without a `/api` suffix) that Next proxies to.

To change Ollama model names or inference options, edit `backend/config/agents.py` — those settings are not controlled by environment variables.

| Variable | Used by | Description | Required | Default (if optional) | How to set |
| --- | --- | --- | --- | --- | --- |
| `CHROMA_HOST` | Backend | Hostname of the ChromaDB server the backend connects to for alert storage. | Optional | `localhost` | `backend/.env` (recommended) or command-line |
| `CHROMA_PORT` | Backend | Port of the ChromaDB server the backend connects to. | Optional | `8000` | `backend/.env` (recommended) or command-line |
| `CHROMA_SERVER_DATA_PATH` | Backend | Filesystem path passed to `chroma run --path`; the backend ensures this directory exists at startup (relative paths are resolved from `backend/`). | Optional | `backend/.chroma_data` | `backend/.env` (recommended) or command-line |
| `BACKEND_RUN_LOGS_DIR` | Backend | Directory where pipeline run logs are written (relative paths are resolved from `backend/`). | Optional | `backend/.logs/pipeline_runs` | `backend/.env` (recommended) or command-line |
| `NEXT_PUBLIC_API_URL` | Frontend | Browser-facing base URL for API requests from the Next.js frontend. | Optional | `/api` | `frontend/.env.local` (recommended) or command-line |
| `BACKEND_URL` | Frontend | Server-side FastAPI origin used by Next.js to proxy `/api/*` rewrites (no `/api` suffix). | Optional | `http://localhost:8080` | `frontend/.env.local` (recommended) or command-line |
| `ALLOWED_DEV_ORIGINS` | Frontend | Comma-separated hostnames or IPs allowed to load Next.js dev assets (HMR) over LAN or Tailscale. | Optional | _(empty — no extra origins)_ | `frontend/.env.local` (recommended) or command-line |
| `NEXT_PUBLIC_USE_MOCK_DATA` | Frontend | When `true`, the frontend serves hard-coded mock alerts instead of calling the backend API. **TODO: remove before final project delivery.** | Optional | `false` (unset) | `npm run dev -- --test` (recommended), `frontend/.env.local`, or command-line |
