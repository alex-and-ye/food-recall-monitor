from __future__ import annotations

import logging
from typing import Any

import httpx

from agents.fetchers.crawler.orchestrator import crawl_source_pages
from agents.fetchers.extraction.cleaning import clean_detail_payload
from agents.fetchers.extraction.date_candidates import select_recent_recall_date
from config.agents import SCRAPER_SOURCES
from models.pipeline_progress import ProgressReporter
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
    reporter: ProgressReporter | None = None,
) -> list[ScrapedRecallRecord]:
    source_config = SCRAPER_SOURCES[source]
    effective_limit = min(limit, source_config.max_pages_per_run)
    if reporter is not None:
        reporter.log(
            stage="source",
            source=source,
            message="Starting source crawl",
            details={
                "effective_limit": effective_limit,
                "max_depth": source_config.max_depth,
                "max_pages_per_run": source_config.max_pages_per_run,
            },
        )
    detail_payloads = await crawl_source_pages(
        source_name=source,
        source_config=source_config,
        client=client,
        reporter=reporter,
    )
    if reporter is not None:
        reporter.log(
            stage="source",
            source=source,
            message="Detail payload extraction finished",
            details={"detail_payload_count": len(detail_payloads)},
        )

    records: list[ScrapedRecallRecord] = []
    for payload in detail_payloads:
        selected_date = select_recent_recall_date(
            payload.get("published_date_candidates", []),
            lookback_days=source_config.lookback_days,
        )
        if selected_date is None:
            if reporter is not None:
                reporter.log(
                    stage="source",
                    source=source,
                    message="Dropped detail payload after date filter",
                    details={
                        "source_url": str(payload.get("source_url", "")),
                        "published_date_candidates": list(payload.get("published_date_candidates", [])),
                    },
                )
            continue

        payload["selected_recall_date"] = selected_date
        payload["selected_recall_date_source"] = _date_candidate_source(payload, selected_date)
        cleaned_payload = clean_detail_payload(payload)
        records.append(ScrapedRecallRecord(source_name=source, payload=cleaned_payload))
        if reporter is not None:
            reporter.log(
                stage="source",
                source=source,
                message="Accepted cleaned payload",
                details={
                    "source_url": cleaned_payload.get("source_url", ""),
                    "selected_recall_date": selected_date,
                    "records_collected": len(records),
                },
            )
        if len(records) >= effective_limit:
            break

    if reporter is not None:
        reporter.log(
            stage="source",
            source=source,
            message="Completed source processing",
            details={
                "records_output": len(records),
                "detail_payload_count": len(detail_payloads),
            },
        )
    return records


async def fetch_sources_sequentially(
    sources: list[str],
    *,
    limit: int,
    reporter: ProgressReporter | None = None,
) -> FetchSourcesResult:
    records: list[ScrapedRecallRecord] = []
    failures: dict[str, str] = {}
    async with httpx.AsyncClient(timeout=30.0, headers=SOURCE_REQUEST_HEADERS, follow_redirects=True) as client:
        for source in sources:
            try:
                records.extend(
                    await fetch_source_records(
                        source,
                        limit=limit,
                        client=client,
                        reporter=reporter,
                    )
                )
            except (KeyError, httpx.HTTPError, ValueError, RuntimeError) as exc:
                failures[source] = str(exc)
                LOGGER.warning("Skipping %s scraper source after fetch failure: %s", source, exc)
                if reporter is not None:
                    reporter.log(
                        stage="source",
                        source=source,
                        message="Source processing failed",
                        details={"error": str(exc)},
                    )
    return FetchSourcesResult(records=records, failures=failures)


def _date_candidate_source(payload: dict[str, Any], selected_date: str) -> str:
    sources = payload.get("published_date_candidate_sources")
    if not isinstance(sources, dict):
        return "generic"
    source = str(sources.get(selected_date, "")).strip()
    return source or "generic"
