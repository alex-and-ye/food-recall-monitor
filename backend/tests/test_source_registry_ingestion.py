from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import httpx

from agents.fetchers.scraper_ingestion import fetch_source_records, resolve_source_config
from db.chroma_source_client import InMemoryScraperSourceConfigStore
from models.scraped_record import ScrapedRecallRecord
from models.scraper_config import ScraperHints, ScraperSourceConfig
from models.source_registry import SourceRegistryDocument


def _document(
    *,
    status: str = "ready",
    seed_urls: list[str] | None = None,
) -> SourceRegistryDocument:
    now = datetime.now(timezone.utc)
    return SourceRegistryDocument(
        source_name="uk",
        homepage_url="https://example.com/",
        country_source="UK",
        config=ScraperSourceConfig(
            base_url="https://example.com",
            allowed_domains=["example.com"],
            seed_urls=seed_urls or ["https://example.com/recalls"],
            max_depth=1,
            max_pages_per_run=5,
            lookback_days=1,
            hints=ScraperHints(detail_page_keywords=["/recalls/"]),
        ),
        discovery_status=status,  # type: ignore[arg-type]
        discovered_at=now,
        updated_at=now,
    )


class ResolveSourceConfigTests(unittest.IsolatedAsyncioTestCase):
    async def test_resolve_returns_ready_document(self) -> None:
        store = InMemoryScraperSourceConfigStore()
        store.upsert_source(_document())
        resolved = await resolve_source_config(
            "uk",
            client=AsyncMock(spec=httpx.AsyncClient),
            source_db=store,
            allow_rediscovery=False,
        )
        self.assertEqual(resolved.config.seed_urls, ["https://example.com/recalls"])

    async def test_resolve_rediscovers_stale_document(self) -> None:
        store = InMemoryScraperSourceConfigStore()
        store.upsert_source(_document(status="stale"))
        rediscovered = _document(seed_urls=["https://example.com/new-listing"])
        with patch(
            "agents.fetchers.scraper_ingestion.discover_source_config",
            new=AsyncMock(return_value=rediscovered),
        ) as discovery:
            resolved = await resolve_source_config(
                "uk",
                client=AsyncMock(spec=httpx.AsyncClient),
                source_db=store,
            )
        discovery.assert_awaited_once()
        self.assertEqual(resolved.config.seed_urls, ["https://example.com/new-listing"])
        self.assertEqual(store.get_source("uk").config.seed_urls, ["https://example.com/new-listing"])


class FetchSourceRecordsRegistryTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_source_records_uses_db_config(self) -> None:
        store = InMemoryScraperSourceConfigStore()
        store.upsert_source(_document())
        payload = {
            "source_url": "https://example.com/recalls/abc?utm_source=test",
            "headings": ["<h2>Risk</h2>"],
            "visible_text": "<p>Recall notice content.</p>",
            "published_date_candidates": ["2026-06-09"],
            "published_date_candidate_sources": {"2026-06-09": "selector"},
        }
        with (
            patch(
                "agents.fetchers.scraper_ingestion.crawl_source_pages",
                new=AsyncMock(return_value=[payload]),
            ),
            patch(
                "agents.fetchers.scraper_ingestion.select_recent_recall_date",
                return_value="2026-06-09",
            ),
        ):
            records = await fetch_source_records(
                "uk",
                limit=10,
                client=AsyncMock(spec=httpx.AsyncClient),
                source_db=store,
            )

        self.assertEqual(len(records), 1)
        self.assertIsInstance(records[0], ScrapedRecallRecord)
        self.assertEqual(records[0].payload["source_url"], "https://example.com/recalls/abc")

    async def test_fetch_source_records_rediscovers_when_zero_details(self) -> None:
        store = InMemoryScraperSourceConfigStore()
        store.upsert_source(_document())
        rediscovered = _document(seed_urls=["https://example.com/better-listing"])
        payload = {
            "source_url": "https://example.com/recalls/abc",
            "headings": ["Risk"],
            "visible_text": "Recall",
            "published_date_candidates": ["2026-06-09"],
            "published_date_candidate_sources": {"2026-06-09": "selector"},
        }
        with (
            patch(
                "agents.fetchers.scraper_ingestion.crawl_source_pages",
                new=AsyncMock(side_effect=[[], [payload]]),
            ),
            patch(
                "agents.fetchers.scraper_ingestion.discover_source_config",
                new=AsyncMock(return_value=rediscovered),
            ) as discovery,
            patch(
                "agents.fetchers.scraper_ingestion.select_recent_recall_date",
                return_value="2026-06-09",
            ),
        ):
            records = await fetch_source_records(
                "uk",
                limit=10,
                client=AsyncMock(spec=httpx.AsyncClient),
                source_db=store,
            )

        discovery.assert_awaited_once()
        self.assertEqual(len(records), 1)
        self.assertEqual(store.get_source("uk").config.seed_urls, ["https://example.com/better-listing"])


if __name__ == "__main__":
    unittest.main()
