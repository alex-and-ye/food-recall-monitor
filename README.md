# Food Recall Monitor

An AI-powered food safety monitoring platform that scrapes, translates, structures, and surfaces multinational food recall and foodborne-illness signals using a locally hosted LLM agent pipeline.

Developed in collaboration with the Canadian Food Inspection Agency (CFIA) as an early-warning proof-of-concept.

---

## Overview

Food safety agencies and consumers face fragmented, multilingual recall information across national websites, press sources, and investigation notices. Food Recall Monitor unifies that signal into a single operational view:

1. **Official recall pipeline** - crawls configured government / consumer-protection recall sites, extracts detail pages, and runs each record through a LangGraph agent swarm (translate → summarize → structure) to produce normalized alerts.
2. **Early-warning discovery pipeline** - searches the open web (Brave Search) for emerging food-safety incidents, ingests candidate pages, scores confidence / trust, and tracks incidents separately from official recalls.
3. **Operator UI** - Next.js dashboard for browsing alerts, statistics, a 3D globe of geocoded events, early-warning incidents, and pipeline operational issues.

Inference runs on **Ollama** on the host machine. Model names and options are configured in code (`backend/config/agents.py`), not via secrets in the environment supporting air-gapped or data-sovereign deployments where cloud LLM APIs are not acceptable.

---

## Key capabilities

| Area | What it does |
| --- | --- |
| Multi-source scraping | Priority-queue crawler with static HTTP + Playwright fallback, robots awareness, and per-source config |
| Automated source discovery | Heuristic + LLM discovery of listing seeds and detail-page URL patterns from a homepage |
| Multilingual processing | Translates scraped payloads to English while preserving JSON structure; adaptive date parsing across languages |
| Structured alerts | Canonical alert schema (product, hazard, risk, regions, consumer action, source URL, etc.) |
| Early-warning discovery | Country/language-aware search queries, candidate ingestion, trust tiers, incident verification |
| Real-time UI updates | Server-sent event streams for alerts and incidents |
| Scheduling | Daily automated runs for official and early-warning pipelines (03:00 local by default) |
| Persistence | ChromaDB collections for alerts, source registry, incidents, candidates, and pipeline run logs |
| Ops visibility | Pipeline warnings (source skips, fetch failures, record skips) with acknowledge workflow |

---

## Architecture

```text
┌─────────────────────────────────────────────────────────────────┐
│  Next.js frontend (:3000)                                       │
│  Alerts · Stats · Globe · Early Warnings · Pipeline Issues      │
│  /api/*  ──rewrite──►  FastAPI                                  │
└───────────────────────────────┬─────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────┐
│  FastAPI backend (:8080)                                        │
│                                                                 │
│  Official pipeline          Early-warning pipeline              │
│  agents/ + services/         Brave Search → ingest →            │
│  scrape → LangGraph →       process → incidents                 │
│  FoodRecallAlertCreate                                          │
│                                                                 │
│  Schedulers · SSE event bus · Warnings · Geocoding              │
└───────────────┬─────────────────────────────┬───────────────────┘
                │                             │
                ▼                             ▼
         ChromaDB (:8000)              Ollama on host (:11434)
         alerts, sources,              qwen2.5:14b (default)
         incidents, logs               (not packaged in Docker)
```

### Official recall pipeline

```text
Source registry  →  crawl listing seeds  →  extract detail HTML
        →  filter by recall-date lookback  →  per-record LangGraph:
              translate → summarize → structure → repair/convert
        →  persist alert (+ geocode, semantic index hooks)
```

Details: [`backend/agents/README.md`](backend/agents/README.md).

### Early-warning pipeline

```text
Country / language query policy (early_warning.yaml)
        →  Brave Search  →  fetch & extract candidate pages
        →  LLM processing / verification  →  EarlyWarningIncident store
```

Enable or disable either pipeline in `backend/config/pipelines.yaml`. Discovery query policy lives in `backend/config/early_warning.yaml`. Secrets (`BRAVE_API_KEY`) stay in `backend/.env`.

---

## Tech stack

| Layer | Technologies |
| --- | --- |
| Frontend | Next.js 16, React 19, TypeScript, Tailwind CSS 4, react-globe.gl / Three.js |
| Backend | FastAPI, LangGraph, httpx, BeautifulSoup, dateparser, Playwright, geopy |
| LLM | Ollama (local); default models `qwen2.5:14b` |
| Data | ChromaDB 1.5.x |
| Deploy | Docker Compose (Chroma + backend + frontend); Ollama on the host |

---

## Repository layout

```text
food-recall-monitor/
├── backend/                 # FastAPI API, agents, pipelines, Chroma access
│   ├── agents/              # Scrape + LLM agent pipeline (see agents/README.md)
│   ├── routes/              # HTTP API surface
│   ├── config/              # agents.py, pipelines.yaml, early_warning.yaml
│   ├── db/                  # Chroma / persistence interfaces
│   ├── models/              # Pydantic / TypedDict domain models
│   ├── services/            # Pipeline orchestration, early warning, geocoding
│   ├── tests/               # Pytest suite
│   └── Dockerfile
├── frontend/                # Next.js operator dashboard
│   ├── src/app/             # Pages: alerts, stats, globe, early-warnings, warnings
│   └── Dockerfile
├── benchmark/               # Offline LLM quality / timing benchmarks (not in Compose)
├── docker-compose.yml       # Production-like full stack
└── README.md                # This file
```

---

## Prerequisites

- **Docker** with Compose v2 (recommended full-stack path), **or** Node 20+ and Python **3.13** for local development
- **[Ollama](https://ollama.com/)** installed and running **on the host** (required for all LLM stages)
- Models pulled to match `backend/config/agents.py` (defaults use `qwen2.5:14b`):

```bash
ollama pull qwen2.5:14b
```

- Optional: `BRAVE_API_KEY` in `backend/.env` when early warning is enabled

---

## Quick start (Docker)

The recommended way to run the full application is Docker Compose from the **repository root**. This starts ChromaDB, the FastAPI backend, and the Next.js frontend.

**Ollama must be installed and running on the host.** It is **not** included in Compose, not built into any image, and not started by `docker compose`. The backend container reaches the host install at `http://host.docker.internal:11434`.

### Layout

| Path | Role |
| --- | --- |
| `docker-compose.yml` | Orchestrates `chroma`, `backend`, and `frontend` |
| `backend/Dockerfile` | Production FastAPI image (includes Playwright Chromium) |
| `frontend/Dockerfile` | Multi-stage Next.js production image (`output: "standalone"`) |
| `backend/.dockerignore` / `frontend/.dockerignore` | Keeps build contexts small |

`benchmark/` is not part of the Compose stack.

### Start the stack

```bash
# from repository root - only after Ollama is installed and running on the host
docker compose up --build
```

Then open **http://localhost:3000**. The UI proxies `/api` to the `backend` service on the Compose network.

| Port | Service |
| --- | --- |
| `3000` | Frontend (primary entry point) |
| `8080` | Backend API (optional direct access; OpenAPI at `/docs`) |
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
- For day-to-day coding you can run frontend/backend on the host (see below) and use Compose for a release-like deploy check.
- With early warning enabled (`config/pipelines.yaml`), put `BRAVE_API_KEY` in `backend/.env` (see `backend/.env.example`). Compose loads that file into the backend container; it is not baked into the image.

---

## Local development

### Backend

See [`backend/README.md`](backend/README.md).

```bash
# Terminal 1 - ChromaDB (data path must match CHROMA_SERVER_DATA_PATH)
chroma run --path ./backend/.chroma_data --port 8000

# Terminal 2 - API
cd backend
# create .venv, pip install -r requirements.txt, copy .env.example → .env
fastapi dev main.py --port 8080
```

### Frontend

See [`frontend/README.md`](frontend/README.md).

```bash
cd frontend
npm install
# copy .env.example → .env.local as needed
npm run dev          # http://localhost:3000
```

### Configuration knobs

| File | Purpose |
| --- | --- |
| `backend/config/agents.py` | LLM model names and Ollama inference options |
| `backend/config/pipelines.yaml` | Enable/disable official and early-warning pipelines; bootstrap-on-empty-DB |
| `backend/config/early_warning.yaml` | Countries, languages, domain trust profiles, search budgets |
| `backend/.env` | Chroma, Ollama host, Brave API key |
| `frontend/.env.local` | API base URL and Next rewrite target |

---

## Frontend surfaces

| Route | Purpose |
| --- | --- |
| `/` | Official recall feed (search, cards, detail pages) |
| `/stats` | Aggregate hazard, category, and region statistics |
| `/globe` | Interactive 3D map of geocoded alerts (desktop-oriented) |
| `/early-warnings` | Discovered early-warning incidents |
| `/warnings` | Pipeline operational issues (acknowledge workflow) |

---

## Backend API (summary)

| Prefix | Role |
| --- | --- |
| `/api/alerts` | List, detail, stats, version, SSE events |
| `/api/sources` | Source registry CRUD and rediscovery |
| `/api/incidents` | Early-warning incidents, stats, SSE events |
| `/api/early-warnings` | Trigger early-warning discovery runs |
| `/api/warnings` | Pipeline warnings and acknowledgement |
| `/health` | Liveness check |

Interactive OpenAPI docs: `http://localhost:8080/docs`.
---

## Environment variables

The table below lists every environment variable read by the application code.

- **Frontend** variables are loaded automatically by Next.js from `frontend/.env`, `frontend/.env.local`, and related files (see `frontend/.env.example`).
- **Backend** variables are loaded from `backend/.env` (see `backend/.env.example`) and from the process environment; shell values override the `.env` file.

When using Next.js API rewrites, keep `NEXT_PUBLIC_API_URL` and `BACKEND_URL` in sync: the browser should call `/api` on the Next server, and `BACKEND_URL` should point at the FastAPI origin (without a `/api` suffix) that Next proxies to.

To change Ollama model names or inference options, edit `backend/config/agents.py` - those settings are not controlled by environment variables.

| Variable | Used by | Description | Required | Default (if optional) | How to set |
| --- | --- | --- | --- | --- | --- |
| `BRAVE_API_KEY` | Backend | Brave Search API key used by the early-warning discovery pipeline. | Required when early warning is enabled | _(none)_ | `backend/.env` (recommended); Compose loads it via `env_file` |
| `CHROMA_HOST` | Backend | Hostname of the ChromaDB server the backend connects to for alert storage. | Optional | `localhost` | `backend/.env` (recommended), Compose, or command-line |
| `CHROMA_PORT` | Backend | Port of the ChromaDB server the backend connects to. | Optional | `8000` | `backend/.env` (recommended), Compose, or command-line |
| `CHROMA_SERVER_DATA_PATH` | Backend | Filesystem path passed to `chroma run --path`; the backend ensures this directory exists at startup (relative paths are resolved from `backend/`). | Optional | `backend/.chroma_data` | `backend/.env` (recommended) or command-line |
| `OLLAMA_HOST` | Backend | Base URL for the Ollama HTTP API (used by the `ollama` Python client). | Optional | `http://127.0.0.1:11434` | Compose (`http://host.docker.internal:11434`), `backend/.env`, or command-line |
| `NEXT_PUBLIC_API_URL` | Frontend | Browser-facing base URL for API requests from the Next.js frontend. | Optional | `/api` | `frontend/.env.local` (recommended), Docker build arg, or command-line |
| `BACKEND_URL` | Frontend | Server-side FastAPI origin used by Next.js to proxy `/api/*` rewrites (no `/api` suffix). In Docker images this is a **build-time** arg. | Optional | `http://localhost:8080` | `frontend/.env.local` (recommended), Docker build arg, or command-line |
| `ALLOWED_DEV_ORIGINS` | Frontend | Comma-separated hostnames or IPs allowed to load Next.js dev assets (HMR) over LAN or Tailscale. | Optional | _(empty - no extra origins)_ | `frontend/.env.local` (recommended) or command-line |

---

## Testing and benchmarking

```bash
# Backend tests (from backend/)
pytest -q

# Frontend lint
cd frontend && npm run lint
```

Offline LLM evaluation (translation / summarization / structuring quality and timing) lives in [`benchmark/`](benchmark/README.md) and is separate from the Compose application stack.

---

## Documentation map

| Document | Contents |
| --- | --- |
| [`backend/README.md`](backend/README.md) | Backend local run, Chroma, Ollama notes |
| [`backend/agents/README.md`](backend/agents/README.md) | Scraper + LangGraph agent package deep dive |
| [`frontend/README.md`](frontend/README.md) | Frontend env, scripts, API rewrite setup |
| [`benchmark/README.md`](benchmark/README.md) | Local LLM benchmark harness |

---

## License

MIT License - Copyright (c) 2026 Alexandr Yermakov and Varun Mulchandani. See [`LICENSE`](LICENSE).

---

## Disclaimer

This project is a **proof-of-concept** for research and operational exploration. It is not a substitute for official food-safety authority guidance. Always verify critical consumer actions against primary government recall notices.
