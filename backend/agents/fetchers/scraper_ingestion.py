"""End-to-end scraper ingestion: config resolution, crawl, filter, and batch fetch.

Resolves or rediscovers source registry entries, crawls listing seeds for detail
pages, filters records by recall date, and exposes sequential multi-source fetch
with per-source failure isolation.
"""

import logging
from typing import Any

import httpx

from agents.fetchers.crawler.orchestrator import crawl_source_pages
from agents.fetchers.crawler.source_discovery import (
    discover_source_config,
    prefer_unfiltered_listing_urls,
)
from agents.fetchers.extraction.cleaning import clean_detail_payload
from agents.fetchers.extraction.date_candidates import select_recent_recall_date
from constants import HTTP_CLIENT_TIMEOUT_SECONDS
from db.source_config_interface import ScraperSourceConfigDBInterface
from models.pipeline_progress import PipelineStage, ProgressReporter
from models.pipeline_result import FetchSourcesResult
from models.scraped_record import ScrapedRecallRecord
from models.scraper_config import DEFAULT_LOOKBACK_DAYS, ScraperSourceConfig
from models.source_registry import DISCOVERY_STATUSES_NEEDING_REFRESH, DiscoveryStatus, SourceRegistryDocument

# Module logger for source fetch and filter diagnostics.
LOGGER = logging.getLogger(__name__)

# Browser-like headers used for all sequential source HTTP requests.
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
    """Wrap a scraped record dict in the translator pipeline envelope shape.

    Args:
        payload: Cleaned detail payload dict from a scraped recall record.

    Returns:
        Dict with a single ``record`` key containing ``payload``.
    """
    return {
        "record": payload,
    }

async def resolve_source_config(
    source: str,
    *,
    client: httpx.AsyncClient,
    source_db: ScraperSourceConfigDBInterface,
    reporter: ProgressReporter | None = None,
    allow_rediscovery: bool = True,
) -> SourceRegistryDocument:
    """Load a source registry document, rediscovering stale or missing configs.

    Args:
        source: Registry source name.
        client: Async HTTP client for discovery fetches.
        source_db: Persistence layer for source registry documents.
        reporter: Optional pipeline progress logger.
        allow_rediscovery: When True, run discovery for missing, stale, or
            seedless documents.

    Returns:
        Ready ``SourceRegistryDocument`` with crawl configuration.

    Raises:
        KeyError: If the source is unknown and cannot be rediscovered.
    """
    document = source_db.get_source(source)
    needs_discovery = (
        document is None
        or document.discovery_status in DISCOVERY_STATUSES_NEEDING_REFRESH
        or not document.config.seed_urls
    )
    if needs_discovery and allow_rediscovery:
        homepage = document.homepage_url if document is not None else None
        if homepage is None:
            raise KeyError(f"Unknown scraper source: {source}")
        if reporter is not None:
            reporter.log(
                stage=PipelineStage.DISCOVERY,
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
        return source_db.upsert_source(discovered)

    if document is None:
        raise KeyError(f"Unknown scraper source: {source}")
    return document

async def fetch_source_records(
    source: str,
    *,
    limit: int,
    client: httpx.AsyncClient,
    source_db: ScraperSourceConfigDBInterface,
    reporter: ProgressReporter | None = None,
) -> list[ScrapedRecallRecord]:
    """Fetch, filter, and return recent recall records for a single source.

    Resolves configuration, optionally broadens filtered listing seeds, crawls
    detail pages, and retries discovery once when a ready source yields zero
    detail payloads.

    Args:
        source: Registry source name.
        limit: Maximum number of records to return.
        client: Shared async HTTP client.
        source_db: Source registry persistence interface.
        reporter: Optional pipeline progress logger.

    Returns:
        Scraped recall records passing date and cleaning filters.
    """
    document = await resolve_source_config(
        source,
        client=client,
        reporter=reporter,
        source_db=source_db,
    )
    source_config = document.config
    preferred_seeds = prefer_unfiltered_listing_urls(
        source_config.seed_urls,
        observed_urls=[document.homepage_url],
    )
    if preferred_seeds != source_config.seed_urls:
        previous_seeds = list(source_config.seed_urls)
        source_config = source_config.model_copy(update={"seed_urls": preferred_seeds})
        document = document.model_copy(update={"config": source_config})
        source_db.upsert_source(document)
        if reporter is not None:
            reporter.log(
                stage=PipelineStage.DISCOVERY,
                source=source,
                message="Broadened filtered listing seeds",
                details={
                    "previous_seed_urls": previous_seeds,
                    "seed_urls": preferred_seeds,
                },
            )
    detail_payloads, records = await _crawl_and_filter(
        source=source,
        source_config=source_config,
        limit=limit,
        client=client,
        reporter=reporter,
    )

    if not detail_payloads and document.discovery_status == DiscoveryStatus.READY:
        # Zero details: mark stale, rediscover once, retry crawl.
        stale = document.touch(status=DiscoveryStatus.STALE, reason="zero detail payloads after crawl")
        source_db.upsert_source(stale)
        if reporter is not None:
            reporter.log(
                stage=PipelineStage.DISCOVERY,
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
        source_db.upsert_source(rediscovered)
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
    """Crawl a source and build date-filtered ``ScrapedRecallRecord`` instances.

    Args:
        source: Registry source name for logging.
        source_config: Crawl configuration and hints.
        limit: Maximum records to collect this run.
        client: Async HTTP client passed to the crawler.
        reporter: Optional pipeline progress logger.

    Returns:
        Tuple of raw detail payloads and accepted scraped records.
    """
    effective_limit = min(limit, source_config.max_pages_per_run)
    if reporter is not None:
        reporter.log(
            stage=PipelineStage.SOURCE,
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
            stage=PipelineStage.SOURCE,
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
    # Apply the current minimum policy to configs persisted by older discovery
    # versions, which may still contain the former one-day value.
    effective_lookback_days = max(source_config.lookback_days, DEFAULT_LOOKBACK_DAYS)
    for payload in detail_payloads:
        selected_date = select_recent_recall_date(
            payload.get("published_date_candidates", []),
            lookback_days=effective_lookback_days,
            candidate_sources=payload.get("published_date_candidate_sources")
            if isinstance(payload.get("published_date_candidate_sources"), dict)
            else None,
        )
        if selected_date is None:
            dropped_by_date += 1
            if reporter is not None:
                reporter.log(
                    stage=PipelineStage.SOURCE,
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
                stage=PipelineStage.SOURCE,
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
            stage=PipelineStage.SOURCE,
            source=source,
            message="Completed source processing",
            details={
                "records_output": len(records),
                "detail_payload_count": len(detail_payloads),
                "dropped_by_date": dropped_by_date,
                "lookback_days": effective_lookback_days,
            },
        )
    return detail_payloads, records

async def fetch_sources_sequentially(
    sources: list[str],
    *,
    limit: int,
    source_db: ScraperSourceConfigDBInterface,
    reporter: ProgressReporter | None = None,
) -> FetchSourcesResult:
    """Fetch records from multiple sources sequentially with isolated failures.

    Args:
        sources: Ordered list of registry source names.
        limit: Per-source record cap passed to ``fetch_source_records``.
        source_db: Source registry persistence interface.
        reporter: Optional pipeline progress logger.

    Returns:
        Aggregated records and a map of source names to error messages for
        sources that failed with recoverable exceptions.
    """
    records: list[ScrapedRecallRecord] = []
    failures: dict[str, str] = {}
    async with httpx.AsyncClient(
        timeout=HTTP_CLIENT_TIMEOUT_SECONDS,
        headers=SOURCE_REQUEST_HEADERS,
        follow_redirects=True,
    ) as client:
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
                        stage=PipelineStage.SOURCE,
                        source=source,
                        message="Source processing failed",
                        details={"error": str(exc)},
                    )
    return FetchSourcesResult(records=records, failures=failures)

def _date_candidate_source(payload: dict[str, Any], selected_date: str) -> str:
    """Return the provenance label for a selected published-date candidate."""
    sources = payload.get("published_date_candidate_sources")
    if not isinstance(sources, dict):
        return "generic"
    source = str(sources.get(selected_date, "")).strip()
    return source or "generic"
