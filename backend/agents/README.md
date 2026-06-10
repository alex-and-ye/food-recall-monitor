# Agents

This package contains the recall ingestion and AI agent pipeline.

## Adding API Sources

API sources are configured in `agents/config.py` under `API_SOURCES`. The
pipeline accepts the keys from that dictionary as `sources` values in
`POST /api/pipeline/run`.

Each source entry is just a name and a JSON API URL:

```python
API_SOURCES = {
    "example": "https://example.com/recalls.json",
}
```

The fetcher infers records from common response shapes: a root list, or nested
lists under keys such as `results`, `items`, `data`, or `records`.

The first agent translates values while preserving the original API keys and
structure. The third agent creates the final recall schema. After Agent 3
responds, `product_name`, `recall_date`, and `source_url` are checked against
string values in the original JSON record. If a protected value was translated,
invented, shortened, or otherwise changed, the pipeline replaces it with the
best matching value from the original record.