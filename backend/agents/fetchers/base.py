"""Compatibility layer for source payload parsing and fetcher re-exports.

Provides a thin ``parse_source_payload`` helper alongside the primary scraper
ingestion entry points for callers that expect a unified fetchers module surface.
"""

from typing import Any

from agents.fetchers.scraper_ingestion import (
    fetch_source_records,
    fetch_sources_sequentially,
    to_translator_envelope,
)
def parse_source_payload(_source: str, payload: Any, *, limit: int) -> list[dict[str, Any]]:
    """Normalize a raw source payload into a bounded list of record dicts.

    Args:
        _source: Source identifier (unused; retained for call-site compatibility).
        payload: Raw fetch result, expected to be a list of dict records.
        limit: Maximum number of records to return.

    Returns:
        Up to ``limit`` dict records from ``payload``; empty list if ``payload``
        is not a list or contains no dict entries.
    """
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
