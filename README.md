# Food Recall Monitor

An AI-powered food safety monitoring platform that uses a locally hosted LLM agent swarm to automatically scrape, translate, classify, and summarize global food recall and foodborne illness reports. Developed in collaboration with the Canadian Food Inspection Agency as an early warning proof-of-concept system.

## Docker (release / deployment)

The recommended way to run the full application stack is Docker Compose from the **repository root**. This starts ChromaDB, the FastAPI backend, and the Next.js frontend.

**Ollama must be installed and running on the host machine** (the computer or VM where you run Docker). It is **not** included in Compose, not built into any image, and not started by `docker compose`. Install Ollama on the host, pull the models listed in `backend/config/agents.py`, then start Compose. The backend container reaches that host install at `http://host.docker.internal:11434`.

### Layout

| Path | Role |
| --- | --- |
| `docker-compose.yml` | Orchestrates `chroma`, `backend`, and `frontend` |
| `backend/Dockerfile` | Production FastAPI image (includes Playwright Chromium) |
| `frontend/Dockerfile` | Multi-stage Next.js production image (`output: "standalone"`) |
| `backend/.dockerignore` / `frontend/.dockerignore` | Keeps build contexts small |

`benchmark/` is not part of the Compose stack.

### Prerequisites

1. Docker with Compose v2
2. **Ollama installed on the host** (not in Docker), with the daemon running and required models pulled — see `backend/config/agents.py`. Without a host Ollama install, the pipeline cannot call the LLM.

### Start the stack

```bash
# from repository root - only after Ollama is installed and running on the host
docker compose up --build
```

Then open **http://localhost:3000**. The UI proxies `/api` to the `backend` service on the Compose network.

Published ports (defaults):

| Port | Service |
| --- | --- |
| `3000` | Frontend (primary entry point) |
| `8080` | Backend API (optional direct access) |
| `8000` | ChromaDB (optional debugging) |

### How services are wired

```text
Browser → frontend:3000  --(rewrite /api)→  backend:8080  →  chroma:8000
                                              ↓
                         Ollama on the host machine (:11434)
                         (must be installed outside Docker)
```

Compose sets `CHROMA_HOST=chroma` and builds the frontend with `BACKEND_URL=http://backend:8080` so containers talk by service name. Change those values in `docker-compose.yml` (and rebuild the frontend image if you change `BACKEND_URL` / `NEXT_PUBLIC_API_URL` build args).

### Notes

- **Ollama is a host dependency**, not a Compose service. Installing Docker alone is not enough for LLM features.
- Pipeline logs persist in the `backend_logs` volume; Chroma data in `chroma_data`.
- For day-to-day coding you can still run frontend/backend on the host (see `frontend/README.md` and `backend/README.md`) and only use Compose for a release-like deploy check.
- With early warning enabled (`config/pipelines.yaml`), put `BRAVE_API_KEY` in `backend/.env` (see `backend/.env.example`). Compose loads that file into the backend container; it is not baked into the image.

## Environment variables

The table below lists every environment variable read by the application code.

- **Frontend** variables are loaded automatically by Next.js from `frontend/.env`, `frontend/.env.local`, and related files (see `frontend/.env.example`).

- **Backend** variables are loaded from `backend/.env` (see `backend/.env.example`) and from the process environment; shell values override the `.env` file.

When using Next.js API rewrites, keep `NEXT_PUBLIC_API_URL` and `BACKEND_URL` in sync: the browser should call `/api` on the Next server, and `BACKEND_URL` should point at the FastAPI origin (without a `/api` suffix) that Next proxies to.

To change Ollama model names or inference options, edit `backend/config/agents.py` — those settings are not controlled by environment variables.

| Variable | Used by | Description | Required | Default (if optional) | How to set |
| --- | --- | --- | --- | --- | --- |
| `BRAVE_API_KEY` | Backend | Brave Search API key used by the early-warning discovery pipeline. | Required when early warning is enabled | _(none)_ | `backend/.env` (recommended); Compose loads it via `env_file` |
| `CHROMA_HOST` | Backend | Hostname of the ChromaDB server the backend connects to for alert storage. | Optional | `localhost` | `backend/.env` (recommended), Compose, or command-line |
| `CHROMA_PORT` | Backend | Port of the ChromaDB server the backend connects to. | Optional | `8000` | `backend/.env` (recommended), Compose, or command-line |
| `CHROMA_SERVER_DATA_PATH` | Backend | Filesystem path passed to `chroma run --path`; the backend ensures this directory exists at startup (relative paths are resolved from `backend/`). | Optional | `backend/.chroma_data` | `backend/.env` (recommended) or command-line |
| `OLLAMA_HOST` | Backend | Base URL for the Ollama HTTP API (used by the `ollama` Python client). | Optional | `http://127.0.0.1:11434` | Compose (`http://host.docker.internal:11434`), `backend/.env`, or command-line |
| `NEXT_PUBLIC_API_URL` | Frontend | Browser-facing base URL for API requests from the Next.js frontend. | Optional | `/api` | `frontend/.env.local` (recommended), Docker build arg, or command-line |
| `BACKEND_URL` | Frontend | Server-side FastAPI origin used by Next.js to proxy `/api/*` rewrites (no `/api` suffix). In Docker images this is a **build-time** arg. | Optional | `http://localhost:8080` | `frontend/.env.local` (recommended), Docker build arg, or command-line |
| `ALLOWED_DEV_ORIGINS` | Frontend | Comma-separated hostnames or IPs allowed to load Next.js dev assets (HMR) over LAN or Tailscale. | Optional | _(empty — no extra origins)_ | `frontend/.env.local` (recommended) or command-line |
| `NEXT_PUBLIC_USE_MOCK_DATA` | Frontend | When `true`, the frontend serves hard-coded mock alerts instead of calling the backend API. **TODO: remove before final project delivery.** | Optional | `false` (unset) | `npm run dev -- --test` (recommended), `frontend/.env.local`, or command-line |
