# Agents

This package contains the recall ingestion and AI agent pipeline.

## Adding API Sources

API sources are configured in `agents/config.py` under `API_SOURCES`. The
pipeline accepts the keys from that dictionary as `sources` values in
`POST /api/pipeline/run`.

Each source entry is either a URL string or a mapping with `url` and optional
per-source `headers`:

```python
API_SOURCES = {
    "example": "https://example.com/recalls.json",
    "protected_api": {
        "url": "https://example.com/recalls.json",
        "headers": {
            "Referer": "https://example.com",
            "Origin": "https://example.com",
        },
    },
}
```

The fetcher infers records from common response shapes: a root list, or nested
lists under keys such as `results`, `items`, `data`, or `records`.

The translation step translates values while preserving the original API keys and
structure. The structuring step creates the final recall schema. After
structuring, `product_name`, `recall_date`, and `source_url` are checked against
string values in the original JSON record. If a protected value was translated,
invented, shortened, or otherwise changed, the pipeline replaces it with the
best matching value from the original record.

## Swappable Models

LLM model names are configured in `agents/config.py`:

- `TRANSLATION_MODEL`
- `SUMMARIZATION_MODEL`
- `STRUCTURING_MODEL`
