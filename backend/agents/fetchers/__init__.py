"""Public fetcher API for scraping recall sources and shaping translator payloads.

Re-exports the core ingestion functions and the ``FetchSourcesResult`` model
used by the pipeline to collect scraped recall records from configured sources.
"""

from agents.fetchers.scraper_ingestion import (
    fetch_source_records,
    fetch_sources_sequentially,
    to_translator_envelope,
)
from models.pipeline_result import FetchSourcesResult

__all__ = [
    "FetchSourcesResult",
    "fetch_source_records",
    "fetch_sources_sequentially",
    "to_translator_envelope",
]
