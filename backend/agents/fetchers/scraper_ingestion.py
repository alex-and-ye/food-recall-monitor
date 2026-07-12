from __future__ import annotations

import logging
from typing import Any

import httpx

from agents.fetchers.crawler.orchestrator import crawl_source_pages
from agents.fetchers.crawler.source_discovery import discover_source_config
from agents.fetchers.extraction.cleaning import clean_detail_payload
from agents.fetchers.extraction.date_candidates import select_recent_recall_date
from db.source_config_interface import ScraperSourceConfigDBInterface
from models.pipeline_progress import ProgressReporter
from models.pipeline_result import FetchSourcesResult
from models.scraped_record import ScrapedRecallRecord
from models.scraper_config import ScraperSourceConfig
from models.source_registry import SourceRegistryDocument

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


def _get_source_db() -> ScraperSourceConfigDBInterface:
    from dependencies import get_source_config_db

    return get_source_config_db()


async def resolve_source_config(
    source: str,
    *,
    client: httpx.AsyncClient,
    reporter: ProgressReporter | None = None,
    source_db: ScraperSourceConfigDBInterface | None = None,
    allow_rediscovery: bool = True,
) -> SourceRegistryDocument:
    db = source_db or _get_source_db()
    document = db.get_source(source)
    needs_discovery = (
        document is None
        or document.discovery_status in {"failed", "stale", "pending"}
        or not document.config.seed_urls
    )
    if needs_discovery and allow_rediscovery:
        homepage = document.homepage_url if document is not None else None
        if homepage is None:
            raise KeyError(f"Unknown scraper source: {source}")
        if reporter is not None:
            reporter.log(
                stage="discovery",
                source=source,
                message="Starting source rediscovery",
                details={"reason": document.discovery_status if document else "missing"},
            )
        discovered = await discover_source_config(
            source_name=source,
            homepage_url=homepage,
            country_source=document.country_source if document else source,
            client=client,
            reporter=reporter,
        )
        return db.upsert_source(discovered)

    if document is None:
        raise KeyError(f"Unknown scraper source: {source}")
    return document


async def fetch_source_records(
    source: str,
    *,
    limit: int,
    client: httpx.AsyncClient,
    reporter: ProgressReporter | None = None,
    source_db: ScraperSourceConfigDBInterface | None = None,
) -> list[ScrapedRecallRecord]:
    db = source_db or _get_source_db()
    document = await resolve_source_config(
        source,
        client=client,
        reporter=reporter,
        source_db=db,
    )
    source_config = document.config
    detail_payloads, records = await _crawl_and_filter(
        source=source,
        source_config=source_config,
        limit=limit,
        client=client,
        reporter=reporter,
    )

    if not detail_payloads and document.discovery_status == "ready":
        # Zero details: mark stale, rediscover once, retry crawl.
        stale = document.touch(status="stale", reason="zero detail payloads after crawl")
        db.upsert_source(stale)
        if reporter is not None:
            reporter.log(
                stage="discovery",
                source=source,
                message="Starting source rediscovery",
                details={"reason": "zero_detail_payloads"},
            )
        rediscovered = await discover_source_config(
            source_name=source,
            homepage_url=document.homepage_url,
            country_source=document.country_source,
            client=client,
            reporter=reporter,
        )
        db.upsert_source(rediscovered)
        _detail_payloads, records = await _crawl_and_filter(
            source=source,
            source_config=rediscovered.config,
            limit=limit,
            client=client,
            reporter=reporter,
        )

    return records


async def _crawl_and_filter(
    *,
    source: str,
    source_config: ScraperSourceConfig,
    limit: int,
    client: httpx.AsyncClient,
    reporter: ProgressReporter | None,
) -> tuple[list[dict[str, object]], list[ScrapedRecallRecord]]:
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
                "seed_urls": source_config.seed_urls,
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
            message="Detail payloads collected",
            details={
                "detail_payload_count": len(detail_payloads),
                "detail_urls": [
                    str(payload.get("source_url", ""))
                    for payload in detail_payloads[:10]
                ],
            },
        )

    records: list[ScrapedRecallRecord] = []
    dropped_by_date = 0
    for payload in detail_payloads:
        selected_date = select_recent_recall_date(
            payload.get("published_date_candidates", []),
            lookback_days=source_config.lookback_days,
        )
        if selected_date is None:
            dropped_by_date += 1
            if reporter is not None:
                reporter.log(
                    stage="source",
                    source=source,
                    message="Dropped detail payload after date filter",
                    details={
                        "source_url": str(payload.get("source_url", "")),
                        "published_date_candidates": list(payload.get("published_date_candidates", []))[:5],
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
                    "selected_recall_date_source": payload.get("selected_recall_date_source", "generic"),
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
                "dropped_by_date": dropped_by_date,
            },
        )
    return detail_payloads, records


async def fetch_sources_sequentially(
    sources: list[str],
    *,
    limit: int,
    reporter: ProgressReporter | None = None,
    source_db: ScraperSourceConfigDBInterface | None = None,
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
                        source_db=source_db,
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
