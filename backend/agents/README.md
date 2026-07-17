# Agents

This package contains the recall ingestion and AI agent pipeline.

## Web sources

Scraper sources are stored in the source registry (bootstrapped from
`BOOTSTRAP_SCRAPER_SOURCES` in `config/agents.py`). The pipeline accepts those
source keys as `sources` values in `POST /api/pipeline/run`.

Each processed alert stores `web_source` (the scraper source key, inserted
deterministically by the pipeline) separately from `country_source` (inferred by
the structuring agent from page context).

The translation step translates values while preserving the scraped JSON keys and
structure. The structuring step creates the final recall schema. After
structuring, `product_name`, `recall_date`, and `source_url` are checked against
string values in the original record. If a protected value was translated,
invented, shortened, or otherwise changed, the pipeline replaces it with the
best matching value from the original record.

## Swappable Models

LLM model names are configured in `config/agents.py`:

- `TRANSLATION_MODEL`
- `SUMMARIZATION_MODEL`
- `STRUCTURING_MODEL`
- `CLASSIFICATION_MODEL`
