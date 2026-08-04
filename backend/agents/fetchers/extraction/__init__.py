"""HTML extraction utilities for recall detail pages.

Re-exports cleaning, date parsing, and structured payload extraction helpers
used by fetchers to turn raw page HTML into normalized detail payloads.
"""

from agents.fetchers.extraction.cleaning import clean_detail_payload
from agents.fetchers.extraction.date_candidates import (
    extract_date_candidates,
    select_recent_recall_date,
)
from agents.fetchers.extraction.date_parser import (
    extract_structured_dates,
    infer_document_languages,
    search_adaptive_dates,
)
from agents.fetchers.extraction.detail_extractor import extract_detail_payload

__all__ = [
    "clean_detail_payload",
    "extract_date_candidates",
    "extract_detail_payload",
    "extract_structured_dates",
    "infer_document_languages",
    "search_adaptive_dates",
    "select_recent_recall_date",
]
