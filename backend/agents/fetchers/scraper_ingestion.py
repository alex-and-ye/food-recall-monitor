from __future__ import annotations

import logging
from typing import Any

import httpx

from agents.fetchers.crawler.orchestrator import crawl_source_pages
from agents.fetchers.extraction.cleaning import clean_detail_payload
from agents.fetchers.extraction.date_candidates import select_recent_recall_date
from config.agents import SCRAPER_SOURCES
from models.pipeline_result import FetchSourcesResult
from models.scraped_record import ScrapedRecallRecord

LOGGER = logging.getLogger(__name__)

SOURCE_REQUEST_HEADERS: dict[str, str] = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
}


def to_translator_envelope(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "record": payload,
    }


async def fetch_source_records(
    source: str,
    *,
    limit: int,
    client: httpx.AsyncClient,
) -> list[ScrapedRecallRecord]:
    source_config = SCRAPER_SOURCES[source]
    effective_limit = min(limit, source_config.max_pages_per_run)
    detail_payloads = await crawl_source_pages(
        source_name=source,
        source_config=source_config,
        client=client,
    )

    records: list[ScrapedRecallRecord] = []
    for payload in detail_payloads:
        selected_date = select_recent_recall_date(
            payload.get("published_date_candidates", []),
            lookback_days=source_config.lookback_days,
        )
        if selected_date is None:
            continue

        payload["selected_recall_date"] = selected_date
        cleaned_payload = clean_detail_payload(payload)
        records.append(ScrapedRecallRecord(source_name=source, payload=cleaned_payload))
        if len(records) >= effective_limit:
            break

    return records


async def fetch_sources_sequentially(
    sources: list[str],
    *,
    limit: int,
) -> FetchSourcesResult:
    records: list[ScrapedRecallRecord] = []
    failures: dict[str, str] = {}
    async with httpx.AsyncClient(timeout=30.0, headers=SOURCE_REQUEST_HEADERS, follow_redirects=True) as client:
        for source in sources:
            try:
                records.extend(
                    await fetch_source_records(source, limit=limit, client=client)
                )
            except (KeyError, httpx.HTTPError, ValueError, RuntimeError) as exc:
                failures[source] = str(exc)
                LOGGER.warning("Skipping %s scraper source after fetch failure: %s", source, exc)
    return FetchSourcesResult(records=records, failures=failures)
