from __future__ import annotations

from typing import Any

from agents.fetchers.scraper_ingestion import (
    fetch_source_records,
    fetch_sources_sequentially,
    to_translator_envelope,
)


def parse_source_payload(_source: str, payload: Any, *, limit: int) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        return []
    cleaned_records = [record for record in payload if isinstance(record, dict)]
    return cleaned_records[:limit]


__all__ = [
    "fetch_source_records",
    "fetch_sources_sequentially",
    "parse_source_payload",
    "to_translator_envelope",
]
