import unittest
from unittest.mock import AsyncMock, patch

import httpx

from agents.fetchers.scraper_ingestion import (
    fetch_source_records,
    fetch_sources_sequentially,
    to_translator_envelope,
)
from models.scraped_record import ScrapedRecallRecord
from models.scraper_config import ScraperHints, ScraperSourceConfig


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
        payload = {
            "source_url": "https://example.com/recalls/abc?utm_source=test",
            "title": "<h1>Original Product</h1>",
            "headings": ["<h2>Risk</h2>"],
            "visible_text": "<p>Recall notice content.</p>",
            "published_date_candidates": ["2026-06-09"],
        }

        with (
            patch("agents.fetchers.scraper_ingestion.SCRAPER_SOURCES", {"uk": source_config}),
            patch(
                "agents.fetchers.scraper_ingestion.crawl_source_pages",
                new=AsyncMock(return_value=[payload]),
            ),
            patch(
                "agents.fetchers.scraper_ingestion.select_recent_recall_date",
                return_value="2026-06-09",
            ),
        ):
            records = await fetch_source_records("uk", limit=10, client=AsyncMock(spec=httpx.AsyncClient))

        self.assertEqual(len(records), 1)
        self.assertIsInstance(records[0], ScrapedRecallRecord)
        self.assertEqual(records[0].source_name, "uk")
        self.assertEqual(records[0].payload["source_url"], "https://example.com/recalls/abc")
        self.assertEqual(records[0].payload["title"], "Original Product")

    async def test_fetch_source_records_skips_records_outside_lookback(self) -> None:
        source_config = ScraperSourceConfig(
            base_url="https://example.com",
            allowed_domains=["example.com"],
            seed_urls=["https://example.com/recalls"],
            lookback_days=1,
            hints=ScraperHints(),
        )
        with (
            patch("agents.fetchers.scraper_ingestion.SCRAPER_SOURCES", {"uk": source_config}),
            patch(
                "agents.fetchers.scraper_ingestion.crawl_source_pages",
                new=AsyncMock(
                    return_value=[
                        {
                            "source_url": "https://example.com/recalls/abc",
                            "title": "A",
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
            records = await fetch_source_records("uk", limit=10, client=AsyncMock(spec=httpx.AsyncClient))
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
        payload = {"title": "Original Product", "visible_text": "Recall content"}
        self.assertEqual(to_translator_envelope(payload), {"record": payload})


if __name__ == "__main__":
    unittest.main()
