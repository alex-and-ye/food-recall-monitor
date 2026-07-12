import unittest
from unittest.mock import AsyncMock, patch

import httpx

from agents.fetchers.scraper_ingestion import (
    fetch_source_records,
    fetch_sources_sequentially,
    to_translator_envelope,
)
from db.chroma_source_client import InMemoryScraperSourceConfigStore
from models.scraped_record import ScrapedRecallRecord
from models.scraper_config import ScraperHints, ScraperSourceConfig
from models.source_registry import SourceRegistryDocument


def _uk_document(source_config: ScraperSourceConfig) -> SourceRegistryDocument:
    return SourceRegistryDocument(
        source_name="uk",
        homepage_url=source_config.base_url,
        country_source="UK",
        config=source_config,
        discovery_status="ready",
    )


class ScraperIngestionTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_source_records_cleans_and_filters_to_recent(self) -> None:
        source_config = ScraperSourceConfig(
            base_url="https://example.com",
            allowed_domains=["example.com"],
            seed_urls=["https://example.com/recalls"],
            max_depth=1,
            max_pages_per_run=5,
            lookback_days=1,
            hints=ScraperHints(),
        )
        store = InMemoryScraperSourceConfigStore()
        store.upsert_source(_uk_document(source_config))
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
        self.assertEqual(records[0].source_name, "uk")
        self.assertEqual(records[0].payload["source_url"], "https://example.com/recalls/abc")
        self.assertNotIn("title", records[0].payload)
        self.assertEqual(records[0].payload["headings"], ["Risk"])
        self.assertEqual(records[0].payload["selected_recall_date_source"], "selector")
        self.assertEqual(records[0].payload["selected_recall_date"], "2026-06-09")
        self.assertNotIn("published_date_candidates", records[0].payload)
        self.assertNotIn("published_date_candidate_sources", records[0].payload)

    async def test_fetch_source_records_skips_records_outside_lookback(self) -> None:
        source_config = ScraperSourceConfig(
            base_url="https://example.com",
            allowed_domains=["example.com"],
            seed_urls=["https://example.com/recalls"],
            lookback_days=1,
            hints=ScraperHints(),
        )
        store = InMemoryScraperSourceConfigStore()
        store.upsert_source(_uk_document(source_config))
        with (
            patch(
                "agents.fetchers.scraper_ingestion.crawl_source_pages",
                new=AsyncMock(
                    return_value=[
                        {
                            "source_url": "https://example.com/recalls/abc",
                            "headings": [],
                            "visible_text": "B",
                            "published_date_candidates": ["2026-06-01"],
                        }
                    ]
                ),
            ),
            patch(
                "agents.fetchers.scraper_ingestion.select_recent_recall_date",
                return_value=None,
            ),
        ):
            records = await fetch_source_records(
                "uk",
                limit=10,
                client=AsyncMock(spec=httpx.AsyncClient),
                source_db=store,
            )
        self.assertEqual(records, [])

    async def test_fetch_sources_sequentially_collects_failures_and_continues(self) -> None:
        with patch(
            "agents.fetchers.scraper_ingestion.fetch_source_records",
            new=AsyncMock(
                side_effect=[
                    [ScrapedRecallRecord(source_name="a", payload={"source_url": "https://a"})],
                    ValueError("boom"),
                    KeyError("missing-source"),
                ]
            ),
        ):
            result = await fetch_sources_sequentially(["a", "b", "c"], limit=10)

        self.assertEqual(len(result.records), 1)
        self.assertIn("b", result.failures)
        self.assertIn("boom", result.failures["b"])
        self.assertIn("c", result.failures)
        self.assertIn("missing-source", result.failures["c"])

    async def test_fetch_sources_sequentially_captures_http_errors(self) -> None:
        with patch(
            "agents.fetchers.scraper_ingestion.fetch_source_records",
            new=AsyncMock(side_effect=httpx.HTTPStatusError("403", request=AsyncMock(), response=AsyncMock())),
        ):
            result = await fetch_sources_sequentially(["us"], limit=5)

        self.assertEqual(result.records, [])
        self.assertIn("us", result.failures)
        self.assertIn("403", result.failures["us"])

    def test_translator_envelope_wraps_cleaned_payload(self) -> None:
        payload = {"headings": ["Original Product"], "visible_text": "Recall content"}
        self.assertEqual(to_translator_envelope(payload), {"record": payload})


if __name__ == "__main__":
    unittest.main()
