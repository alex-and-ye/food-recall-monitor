# Agents

LLM-driven ingestion and processing for official food-recall web sources.

This package scrapes government / consumer-protection recall sites, discovers crawl configuration when needed, extracts detail-page content, and runs each record through a LangGraph agent pipeline that produces structured `FoodRecallAlertCreate` alerts.

Downstream orchestration (persistence, progress tracking, geocoding) lives in `services/pipeline.py`, which calls into this package.

---

## High-level flow

```text
PipelineRunOptions (sources, limit)
        │
        ▼
┌───────────────────────┐
│  Source fetch         │  fetchers/
│  resolve config →     │  discovery / crawl / extract / filter
│  crawl → clean → date │
└───────────┬───────────┘
            │  list[ScrapedRecallRecord]
            ▼
┌───────────────────────┐
│  Per-record graph     │  graph.py (LangGraph)
│  translate → summarize│
│  → structure → repair │
└───────────┬───────────┘
            │
            ▼
    FoodRecallAlertCreate
```

Entry point: `agents.graph.run_pipeline`.

1. **Fetch** — resolve each source’s registry config (rediscover if stale), crawl listing seeds, extract detail payloads, filter by recall date lookback.
2. **Process** — for each `ScrapedRecallRecord`, run the compiled LangGraph nodes.
3. **Emit** — optionally call `on_alert_processed` / `on_warning`; return `AgentPipelineResult`.

If every source fails and no records are fetched, `run_pipeline` raises `SourceFetchError`.

---

## Package layout

```text
agents/
├── graph.py                 # LangGraph pipeline + run_pipeline orchestrator
├── llm.py                   # Ollama chat_text / chat_json helpers
├── prompts.py               # System prompts for LLM stages + discovery
├── validators.py            # Structural checks on agent outputs
├── converters.py            # structured JSON → FoodRecallAlertCreate
├── errors.py                # SourceFetchError
├── normalizers/
│   └── protected_fields.py  # Text cleaning and date parsing for alert fields
└── fetchers/
    ├── scraper_ingestion.py # Multi-source fetch, config resolve, date filter
    ├── base.py              # Compatibility helpers for source payloads
    ├── crawler/
    │   ├── source_discovery.py  # Homepage → ScraperSourceConfig
    │   ├── orchestrator.py      # Priority-queue crawl
    │   ├── discovery.py         # Page class, link extraction, URL rules
    │   └── scoring.py           # URL / page relevance scores
    ├── extraction/
    │   ├── detail_extractor.py  # HTML → headings, text, date candidates
    │   ├── date_parser.py       # Adaptive / structured date parsing
    │   ├── date_candidates.py   # Select recall date within lookback
    │   └── cleaning.py          # Normalize / sanitize detail payloads
    └── rendering/
        ├── static_fetch.py      # httpx HTML fetch
        └── browser_fetch.py     # Playwright fallback for dynamic pages
```

---

## Agent pipeline (`graph.py`)

### `run_pipeline`

```python
await run_pipeline(
    options,                    # PipelineRunOptions: sources + limit
    source_db=...,              # ScraperSourceConfigDBInterface
    reporter=...,               # optional ProgressReporter
    on_alert_processed=...,     # optional sync/async callback per alert
    on_warning=...,             # optional skip / failure notifications
    run_id=...,                 # optional id for warning correlation
) -> AgentPipelineResult
```

Returns alerts produced, `records_fetched`, and per-source `source_failures`.

### Graph nodes

Built by `create_pipeline_graph`. State type: `PipelineRecordState`
(`record` → `translated_json` → `summary` → `structured_json` → `alert`).

| Node | Role | Model config |
|------|------|--------------|
| `translate_values` | Translate natural-language string values to English; preserve JSON shape | `TRANSLATION_MODEL` |
| `summarize` | Exactly three sentences: product, risk, consumer action | `SUMMARIZATION_MODEL` |
| `structure` | Map summary + translated JSON into alert fields | `STRUCTURING_MODEL` |
| `repair_and_convert` | Prefer protected fields from the scrape; convert to `FoodRecallAlertCreate` | (deterministic) |

**Structuring retries:** up to `STRUCTURING_AGENT_MAX_ATTEMPTS` (2). On repeated validation failure, `_fallback_structured_json` builds a minimal object from the scraped payload and summary so the pipeline can continue.

**Repair preferences:** product name, recall date, and source URL prefer values grounded in the original scrape over LLM invention when a reliable original is available.

---

## Fetchers

Public API (`agents.fetchers`):

- `fetch_sources_sequentially` — fetch many sources; isolate failures per source
- `fetch_source_records` — resolve config, crawl, filter, return records for one source
- `to_translator_envelope` — wrap a cleaned payload as `{"record": ...}` for translation

### Source config resolution

`resolve_source_config` loads a `SourceRegistryDocument` from the DB. It rediscovers when the document is missing, marked for refresh (`DISCOVERY_STATUSES_NEEDING_REFRESH`), or has empty `seed_urls`.

Rediscovery uses `discover_source_config` and upserts the result via `source_db`.

### Crawl (`crawler/orchestrator.py`)

`crawl_source_pages`:

1. Seeds a min-heap priority queue from `seed_urls` (relevance-scored).
2. Fetches pages up to `max_pages_per_run` / `max_depth`.
3. Respects `allowed_domains`, `blocked_paths` (seeds bypass blocked paths), and robots.txt when available.
4. Prefers static `httpx` fetch; falls back to Playwright when content looks dynamic or `hints.force_browser` is set.
5. Classifies pages; extracts detail payloads; enqueues keyword-matching child links.

Page classification and link helpers: `crawler/discovery.py`.  
Relevance scoring: `crawler/scoring.py`.

### Source discovery (`crawler/source_discovery.py`)

Automated homepage → crawl config:

1. Derive `base_url` / `allowed_domains`.
2. Explore internal links with structural heuristics (path shape, peer density, asset noise filters).
3. Rank candidates; ask the LLM (`LISTING_DISCOVERY_SYSTEM_PROMPT`) for listing seed URLs.
4. Sample listing children; ask the LLM (`DETAIL_PATTERN_DISCOVERY_SYSTEM_PROMPT`) for detail-page keywords.
5. Assemble a `SourceRegistryDocument` with `ScraperSourceConfig` + discovery status/reason.

Also used by `services/sources.py` for admin / bootstrap flows.

### Extraction

| Module | Responsibility |
|--------|----------------|
| `detail_extractor.py` | Headings, visible text, published-date candidates (DOM, `<time>`, JSON-LD, selectors) |
| `date_parser.py` | Language inference; adaptive `dateparser` search; structured date normalization |
| `date_candidates.py` | Choose a non-future recall date within `lookback_days` |
| `cleaning.py` | Strip HTML, normalize text/URLs, assert cleaned payloads |

Typical detail payload fields:

- `source_url`
- `headings`
- `visible_text`
- `published_date_candidates` / `published_date_candidate_sources`
- after filtering: `selected_recall_date`

### Rendering

- **Static:** `fetch_static_html` / `fetch_static_page` via `httpx`.
- **Browser:** `fetch_browser_html` via Playwright (async, with sync fallback for nested event-loop cases).

Shared browser-like headers for sequential fetches: `SOURCE_REQUEST_HEADERS` in `scraper_ingestion.py`.

---

## LLM layer

### Models (`config/agents.py`)

Model names and Ollama options are **code-configured**, not env vars:

| Constant | Used for |
|----------|----------|
| `TRANSLATION_MODEL` | Value translation |
| `SUMMARIZATION_MODEL` | Three-sentence summary |
| `STRUCTURING_MODEL` | Alert field JSON |
| `CLASSIFICATION_MODEL` | Listing / detail-pattern discovery |
| `OLLAMA_OPTIONS` | temperature, context length, GPU layers |

Default in-repo values use `qwen2.5:14b` with `temperature: 0.0`.

### Helpers (`llm.py`)

- `chat_text` — plain-text replies (summarization)
- `chat_json` — JSON object replies (`format="json"`); raises `AgentOutputError` on bad output

Requires a running [Ollama](https://ollama.com/) instance with the configured models pulled.

### Prompts (`prompts.py`)

| Prompt | Stage |
|--------|--------|
| `TRANSLATION_SYSTEM_PROMPT` | Translate string values only; keep structure |
| `SUMMARIZATION_SYSTEM_PROMPT` | Three-sentence public summary |
| `STRUCTURING_SYSTEM_PROMPT` | Schema for alert fields (risk levels, country examples) |
| `LISTING_DISCOVERY_SYSTEM_PROMPT` | Pick listing seed URLs from ranked candidates |
| `DETAIL_PATTERN_DISCOVERY_SYSTEM_PROMPT` | Infer detail-page URL keywords |

---

## Validation and conversion

**`validators.py`**

- `validate_translated_structure` — translation must not change key set / nesting
- `validate_summary` — non-empty text
- `validate_structured_json` — required fields present; no `alert_id`; `affected_regions` is a list

Required structured fields include: `product_name`, `product_category`, `recall_reason`, `summary`, `recall_date`, `risk_level`, `hazard_type`, `consumer_action`, `source_url`, `batch_id`, `country_source`, `affected_regions`.

**`converters.py`**

`structured_json_to_alert_create` validates, cleans text, parses dates, and builds `FoodRecallAlertCreate`.

**`normalizers/protected_fields.py`**

Shared helpers: `clean_text`, `parse_source_date`, `first_text`, `split_source_list` — used when preferring scrape-grounded values during repair.

---

## Data models (outside this package)

| Model | Module | Role |
|-------|--------|------|
| `PipelineRunOptions` | `models.pipeline_options` | Sources + per-run limit |
| `PipelineRecordState` | `models.pipeline_state` | LangGraph per-record state |
| `ScrapedRecallRecord` | `models.scraped_record` | `source_name` + payload dict |
| `ScraperSourceConfig` / `ScraperHints` | `models.scraper_config` | Seeds, domains, depth, lookback, keywords |
| `SourceRegistryDocument` | `models.source_registry` | Persisted discovery result + config |
| `AgentPipelineResult` | `models.pipeline_result` | Alerts + fetch stats + failures |
| `FoodRecallAlertCreate` | `models.food_recall_alert` | Final alert create schema |

Important `ScraperSourceConfig` knobs:

- `seed_urls`, `allowed_domains`, `base_url`
- `max_depth`, `max_pages_per_run`
- `lookback_days` (1–7)
- `hints.detail_page_keywords`, `date_selectors`, `date_languages`, `blocked_paths`, `force_browser`
- optional `proxy_url`, `request_headers`

---

## How the rest of the backend uses this

| Consumer | Usage |
|----------|--------|
| `services/pipeline.py` | Official pipeline: `run_pipeline` → save alerts, geocode, progress logs |
| `services/sources.py` | Source admin: `discover_source_config`, `derive_base_url_and_domains` |
| `services/source_bootstrap.py` | Bootstrap helpers via `derive_base_url_and_domains` |
| `services/early_warning/` | Reuses rendering, extraction, translation helpers (separate graph) |

---

## Errors

| Exception | When |
|-----------|------|
| `SourceFetchError` | All sources failed and zero records fetched |
| `AgentOutputError` | LLM returned invalid / non-object JSON |
| `AgentValidationError` | Translation shape, empty summary, or structured schema failure |

Per-source fetch errors are collected in `FetchSourcesResult.failures` / `AgentPipelineResult.source_failures` and surfaced as warnings when `on_warning` is provided; they do not abort other sources.

---

## Dependencies and runtime expectations

- **Ollama** — local inference for all LLM stages (see backend README).
- **httpx** — static page fetches.
- **Playwright** — browser fallback for JS-heavy pages.
- **BeautifulSoup** / **dateparser** — HTML and multilingual dates.
- **LangGraph** — per-record agent graph.

Ensure configured Ollama models are available before running the official pipeline.

---

## Tests

Agent-related tests under `backend/tests/` include:

- `test_pipeline_graph.py` — graph nodes / `run_pipeline` behavior
- `test_fetchers.py`, `test_crawler_orchestrator.py` — ingestion and crawl
- `test_source_discovery.py`, `test_discovery_heuristics.py`, `test_page_discovery.py` — discovery
- `test_detail_extractor.py`, `test_date_candidates.py`, `test_cleaning.py` — extraction
- `test_prompts.py` — prompt constants / contracts

From `backend/`:

```bash
pytest tests/test_pipeline_graph.py tests/test_fetchers.py tests/test_source_discovery.py -q
```

---

## Extending

**New LLM stage or prompt change** — edit `prompts.py`, wire the node in `graph.py`, and keep validators/converters aligned with the schema.

**Swap models** — change constants in `config/agents.py` only; do not put model names in `.env`.

**New scrape source** — register a homepage in the source registry; discovery can produce seeds and detail keywords. Tune `ScraperHints` (`detail_page_keywords`, `date_selectors`, `blocked_paths`, `force_browser`) when heuristics need help.

**Reuse pieces outside the official pipeline** — import from `agents.fetchers`, `agents.llm`, or `agents.prompts` as early-warning already does; prefer the public `__init__` re-exports when available.
