# Backend

FastAPI service for **Food Recall Monitor**. It scrapes official government recall sites, runs a local Ollama agent pipeline to normalize recalls into structured alerts, discovers early-warning food-safety signals via Brave Search, and exposes HTTP APIs (plus SSE) for the frontend.

All durable state is stored in **ChromaDB**. Heavy LLM work talks to **Ollama on the host** (not bundled with this service).

For the full Docker Compose stack (Chroma + backend + frontend), see the [repository root README](../README.md).

---

## Purpose

At a high level the backend:

1. **Official recall pipeline** — crawl configured FR / UK / DE recall sites, extract detail pages, run a LangGraph agent chain (translate → summarize → structure → repair), geocode, and persist alerts.
2. **Early-warning discovery** — generate search queries, call Brave Search, ingest candidate pages, structure them into incidents, score confidence, optionally merge semantically, and verify against official alerts.
3. **HTTP API** — serve alerts, incidents, scraper sources, and pipeline warnings; stream change events over SSE; manually trigger early-warning runs.
4. **Schedulers & bootstrap** — daily runs at **03:00 local time**, plus optional empty-DB bootstrap on startup (controlled by `config/pipelines.yaml`).

---

## Folder and file structure

```text
backend/
├── main.py                 # FastAPI app: CORS, routers, lifespan (bootstrap + schedulers)
├── settings.py             # pydantic-settings: Chroma, Brave, optional config path overrides
├── dependencies.py         # Process-wide DI: DB clients, services, locks, SSE broadcasters
├── bootstrap.py            # Empty-DB bootstrap for official + early-warning pipelines
├── scheduler.py            # Daily 03:00 loops for both pipelines
├── pipeline_runner.py      # Thin wrappers: run pipeline + write run logs
├── paths.py                # Resolve/create Chroma data directories
├── constants.py            # Shared non-env constants (e.g. HTTP timeout)
├── requirements.txt        # Pinned Python dependencies
├── Dockerfile              # python:3.13-slim image with Playwright Chromium; uvicorn :8080
├── .env.example            # Template for CHROMA_*, BRAVE_*, config path overrides
├── .dockerignore
├── .gitignore
│
├── config/                 # Static Python config + YAML policy files
│   ├── agents.py           # Ollama model names and generation options
│   ├── sources.py          # Bootstrap homepage URLs for FR/UK/DE scrapers
│   ├── pipelines.py        # Loader for pipelines.yaml
│   ├── pipelines.yaml      # Enable/disable + bootstrap switches for both pipelines
│   ├── early_warning.py    # Schema + loader for early_warning.yaml
│   └── early_warning.yaml  # Countries, budgets, Brave/crawl/confidence/semantic policy
│
├── agents/                 # Official scrape + LLM graph (see agents/README.md)
│   ├── graph.py            # LangGraph orchestration
│   ├── llm.py, prompts.py, validators.py, converters.py, errors.py
│   ├── fetchers/           # Crawl, render, extract official pages
│   └── normalizers/        # Deterministic field cleanup
│
├── db/                     # Repository interfaces + Chroma (and in-memory) implementations
│   ├── interface.py / chroma_client.py                         # Official alerts
│   ├── source_config_interface.py / chroma_source_client.py    # Scraper registry
│   ├── warnings_interface.py / chroma_warnings_client.py       # Pipeline warnings
│   ├── pipeline_logs_interface.py / chroma_pipeline_logs_client.py
│   ├── early_warning_interface.py / chroma_early_warning_client.py
│   └── early_warning_candidate_interface.py / chroma_early_warning_candidates.py
│
├── models/                 # Pydantic domain models (alerts, incidents, pipeline state, …)
├── routes/                 # FastAPI routers mounted under /api/*
│   ├── alerts.py           # /api/alerts (+ stats, version, SSE events)
│   ├── sources.py          # /api/sources CRUD + rediscovery
│   ├── warnings.py         # /api/warnings list/ack
│   ├── incidents.py        # /api/incidents (+ stats, version, SSE events)
│   └── early_warning.py    # POST /api/early-warnings/run
│
├── services/               # Business logic between routes and db/agents
│   ├── alerts.py, sources.py, source_bootstrap.py, warnings.py
│   ├── pipeline.py         # Official PipelineService → agents.graph + Chroma + geocode
│   ├── pipeline_progress.py, alert_events.py, geocoding.py
│   └── early_warning/      # Discovery orchestration, Brave, confidence, verification, …
│
└── tests/                  # pytest coverage for pipelines, fetchers, APIs, Chroma clients
```

### Package roles

| Package | Role |
| --- | --- |
| `config/` | Swappable policy: which pipelines run, which models Ollama uses, scraper seed URLs, early-warning budgets |
| `agents/` | Fetching and LLM transformation for **official** recalls |
| `db/` | Persistence contracts and Chroma-backed stores (in-memory fallbacks where implemented) |
| `models/` | Shared request/response and pipeline data shapes |
| `routes/` | Thin HTTP layer; delegates to services via `dependencies.py` |
| `services/` | Orchestration, domain rules, early-warning subsystem |
| `tests/` | Automated tests (excluded from the Docker image build context) |

---

## Architecture

### Layering

```text
HTTP client
    ↓
routes/          (FastAPI endpoints)
    ↓
services/        (orchestration & domain logic)
    ↓
db/  ·  agents/  ·  external APIs (Ollama, Brave, geocoding)
```

`dependencies.py` constructs Chroma clients and services once at process start. `main.py` lifespan starts bootstrap and daily schedulers; those call `pipeline_runner.py`, which invokes the same services used by the API.

### Request path (API)

```text
Client → routes/* → dependencies.get_* → services/* → db/* (Chroma)
                 ↘ SSE broadcasters (alert / incident change events)
                 ↘ POST /api/early-warnings/run → EarlyWarningPipelineService
```

| Prefix | Primary service | Storage |
| --- | --- | --- |
| `/api/alerts` | `AlertsService` | `food_recall_alerts_collection` |
| `/api/sources` | `SourcesService` | `scraper_sources_collection` |
| `/api/warnings` | `WarningsService` | `pipeline_warnings_collection` |
| `/api/incidents` | `EarlyWarningIncidentService` | `early_warning_incidents_collection` |
| `/api/early-warnings/run` | `EarlyWarningPipelineService` | candidates + incidents (+ warnings) |
| `/`, `/health` | — | liveness |

There is **no** HTTP trigger for the official pipeline; it runs via startup bootstrap, the daily scheduler, or direct service use.

### Official pipeline path

```text
lifespan / scheduler (03:00) / bootstrap
    → pipeline_runner.run_pipeline_wrapper
    → PipelineService.run_pipeline
    → agents.graph.run_pipeline
         → fetchers (crawl / render / extract)
         → LangGraph: translate → summarize → structure → repair_and_convert
         → Ollama (models from config/agents.py)
    → save alerts + geocode → Chroma
    → optional incident verification + SSE notify
```

Official and early-warning runs share a process-wide lock so heavy jobs do not overlap.

### Early-warning path

```text
scheduler / bootstrap / POST /api/early-warnings/run
    → pipeline_runner.run_early_warning_wrapper
    → EarlyWarningPipelineService
         → query generation → Brave Search → candidate store
         → page ingestion → EW processing graph (Ollama)
         → incident save / merge / confidence
         → verify against official alerts
```

### Chroma collections

| Collection | Purpose |
| --- | --- |
| `food_recall_alerts_collection` | Official structured alerts |
| `scraper_sources_collection` | Scraper source registry |
| `pipeline_warnings_collection` | Operator-facing pipeline warnings |
| `pipeline_run_logs_collection` | Pipeline run history / progress |
| `early_warning_incidents_collection` | Early-warning incidents |
| `early_warning_candidates_collection` | Discovery candidates |
| `early_warning_queries_collection` | Query pagination / state |
| `safety_event_similarity_v1` | Optional semantic similarity index |

### Key config touchpoints

- **Enable/disable pipelines:** `config/pipelines.yaml` only (not environment variables).
- **LLM models:** `config/agents.py` (`TRANSLATION_MODEL`, `SUMMARIZATION_MODEL`, `STRUCTURING_MODEL`, `CLASSIFICATION_MODEL`; currently `qwen2.5:14b`).
- **Early-warning policy:** `config/early_warning.yaml` (countries, budgets, Brave/crawl/confidence/semantic settings). Secrets stay in `.env`.
- **Scraper seed URLs:** `config/sources.py`.

---

## Setup

### Prerequisites

1. **Python 3.13** (matches the Docker image base).
2. **ChromaDB** reachable over HTTP (default `localhost:8000`).
3. **Ollama** installed and running on the host, with required models pulled (see `config/agents.py`).
4. **Brave Search API key** in `backend/.env` when early warning is enabled in `config/pipelines.yaml`.
5. **Playwright Chromium** for JS-rendered scrape pages (`playwright install chromium`).

### Local development

```bash
cd backend
python -m venv .venv

# Windows
.\.venv\Scripts\activate
# macOS / Linux
# source .venv/bin/activate

pip install -r requirements.txt
playwright install chromium

copy .env.example .env   # Windows
# cp .env.example .env   # macOS / Linux
# Edit .env: set BRAVE_API_KEY if early warning is enabled
```

Start Chroma (data path must match `CHROMA_SERVER_DATA_PATH`, default `backend/.chroma_data`):

```bash
# from backend/
chroma run --path .chroma_data --port 8000

# or from repo root
chroma run --path ./backend/.chroma_data --port 8000
```

Ensure Ollama is running and the models in `config/agents.py` are available (e.g. `ollama pull qwen2.5:14b`).

Start the API:

```bash
# from backend/
fastapi dev main.py --port 8080

# or
uvicorn main:app --host 0.0.0.0 --port 8080
```

Health check: `GET http://localhost:8080/health`.

### Environment variables

Copy `.env.example` to `.env`. Common values:

| Variable | Description | Default |
| --- | --- | --- |
| `CHROMA_HOST` | Chroma HTTP host | `localhost` |
| `CHROMA_PORT` | Chroma HTTP port | `8000` |
| `CHROMA_SERVER_DATA_PATH` | Chroma server data directory (relative paths resolve from `backend/`) | `.chroma_data` |
| `BRAVE_API_KEY` | Brave Search credential (required when early warning is enabled) | _(none)_ |
| `BRAVE_SEARCH_BASE_URL` | Brave Search API base URL | Brave default |
| `PIPELINE_SWITCHES_PATH` | Override path to `pipelines.yaml` | `config/pipelines.yaml` |
| `EARLY_WARNING_CONFIG_PATH` | Override path to `early_warning.yaml` | `config/early_warning.yaml` |
| `OLLAMA_HOST` | Ollama HTTP base URL (used by the `ollama` client) | `http://127.0.0.1:11434` |

Pipeline enable flags and bootstrap-on-empty-DB behavior are **not** env vars — edit `config/pipelines.yaml`.

### Docker

- **Full stack:** from the repo root, `docker compose up --build` (see [root README](../README.md)). Compose expects Ollama on the **host** at `host.docker.internal:11434`.
- **Backend image alone:** `Dockerfile` builds `python:3.13-slim`, installs deps + Playwright Chromium, and runs `uvicorn main:app --host 0.0.0.0 --port 8080`.

### Tests

```bash
cd backend
pytest
```

---

## Related docs

- [agents/README.md](agents/README.md) — official scrape + agent pipeline package
- [Root README](../README.md) — Docker Compose, env table for the whole monorepo
