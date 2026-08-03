# Agents

Official recall **ingestion and LLM agent pipeline**. This package fetches pages from configured government recall sites, cleans them into structured payloads, and runs a LangGraph chain against local Ollama models to produce `FoodRecallAlertCreate` records.

It is invoked by `services/pipeline.py` (via bootstrap, the daily scheduler, or direct service use). Early-warning discovery lives under `services/early_warning/`, not here.

For backend-wide setup (Python, Chroma, Ollama, env vars), see [../README.md](../README.md).

---

## Purpose

1. **Fetch** — load scraper configs from the source registry, crawl listing pages, open detail pages (static HTTP or Playwright), and extract cleaned text/date payloads.
2. **Transform** — run sequential LLM agents: translate values to English → summarize → structure into alert fields → repair/validate and convert to the domain model.
3. **Report** — emit progress and warnings back to the calling `PipelineService` without owning persistence (Chroma saves happen in services).

---

## Folder and file structure

```text
agents/
├── graph.py              # LangGraph: translate → summarize → structure → repair_and_convert
├── llm.py                # Thin ollama.chat wrappers (text + JSON)
├── prompts.py            # System prompts for each agent step
├── validators.py         # Structural checks on LLM outputs
├── converters.py         # Structured JSON → FoodRecallAlertCreate
├── errors.py             # SourceFetchError and related failures
│
├── fetchers/
│   ├── base.py           # Shared fetcher types / helpers
│   ├── scraper_ingestion.py  # Orchestrates multi-source fetch; public entrypoints
│   ├── crawler/
│   │   ├── orchestrator.py     # Crawl loop: discover links, score, visit details
│   │   ├── discovery.py        # Classify index vs detail pages; extract links
│   │   ├── scoring.py          # Prioritize candidate URLs
│   │   └── source_discovery.py # Bootstrap / rediscover scraper config from a homepage
│   ├── extraction/
│   │   ├── detail_extractor.py # Pull headings, visible text, date signals from HTML
│   │   ├── cleaning.py         # Strip HTML / normalize extracted fields
│   │   ├── date_candidates.py  # Choose the best recall date from candidates
│   │   └── date_parser.py      # Locale-aware date parsing
│   └── rendering/
│       ├── static_fetch.py     # HTTP GET + HTML for static pages
│       └── browser_fetch.py    # Playwright Chromium for JS-rendered pages
│
└── normalizers/
    └── protected_fields.py     # Deterministic cleanup (dates, text) that LLMs must not invent
```

| Path | Purpose |
| --- | --- |
| `graph.py` | Compiles and runs the agent graph; coordinates fetch → per-record LLM steps |
| `llm.py` | Single place that talks to Ollama |
| `prompts.py` | Prompt text only; model names live in `config/agents.py` |
| `fetchers/` | Everything between “source URL” and “clean scraped payload” |
| `normalizers/` | Non-LLM field hygiene used during conversion/repair |

---

## Architecture

### How this package fits the backend

```text
services/pipeline.py
    → agents.graph.run_pipeline
         → fetchers.scraper_ingestion (crawl / render / extract)
         → LangGraph nodes (llm + prompts + validators)
         → converters → FoodRecallAlertCreate
    ← AgentPipelineResult + warnings / progress callbacks
services/pipeline.py then saves to db/ and geocodes
```

Dependencies flow **inward**:

- `graph.py` depends on `fetchers`, `llm`, `prompts`, `validators`, `converters`, and `config.agents` for model names.
- `fetchers` depend on scraper config from `db` (passed in), HTML tooling (BeautifulSoup / Playwright), and extraction helpers.
- `llm.py` depends only on the `ollama` client and `config.agents` options.
- Callers outside this package should use `graph.run_pipeline` / `fetchers` public exports — not reach into crawler internals unless extending fetch behavior.

### Agent graph

```text
START
  → translate_values   (JSON value translation to English)
  → summarize          (fixed-length public summary)
  → structure          (extract typed alert fields as JSON)
  → repair_and_convert (validate, repair gaps, build FoodRecallAlertCreate)
  → END
```

Fetch runs **before** the graph: sources are scraped sequentially, then each record is passed through the compiled graph. Structuring may retry up to `STRUCTURING_AGENT_MAX_ATTEMPTS` (see `graph.py`).

### Web sources

Bootstrap homepage URLs (used when the source registry is empty) are defined in `config/sources.py`:

| Source | Homepage |
| --- | --- |
| France | `https://rappel.conso.gouv.fr/` |
| UK | `https://alerts.food.gov.uk/news-alerts` |
| Germany | `https://www.lebensmittelwarnung.de/DE/Home/home_node.html` |

Full listing/detail patterns are **discovered** at runtime (`fetchers/crawler/source_discovery.py`) and stored in Chroma via the scraper source registry — not hard-coded as complete site maps in this package.

### Swappable models

LLM model names and shared generation options are configured in [`config/agents.py`](../config/agents.py), not via environment variables:

| Constant | Role | Current default |
| --- | --- | --- |
| `TRANSLATION_MODEL` | Translate scraped string values to English | `qwen2.5:14b` |
| `SUMMARIZATION_MODEL` | Write the public-facing summary | `qwen2.5:14b` |
| `STRUCTURING_MODEL` | Extract structured alert JSON | `qwen2.5:14b` |
| `CLASSIFICATION_MODEL` | Risk / hazard classification (shared config) | `qwen2.5:14b` |
| `OLLAMA_OPTIONS` | `temperature`, `num_ctx`, `num_gpu`, … | see file |

Pull matching models into the local Ollama daemon before running the official pipeline.

---

## Setup

This package has **no separate install**. Use the parent backend setup:

1. Install `backend/requirements.txt` and Playwright Chromium.
2. Run Ollama and pull the models listed in `config/agents.py`.
3. Ensure scraper sources exist (bootstrap via `services/source_bootstrap.py` / app lifespan, or `/api/sources`).

There is no standalone CLI entrypoint here; drive the pipeline through the backend service layer or app lifespan/scheduler.
