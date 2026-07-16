from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

import httpx

from agents.fetchers.crawler.orchestrator import crawl_source_pages
from agents.fetchers.crawler.source_discovery import discover_source_config
from models.scraper_config import ScraperHints, ScraperSourceConfig
from services.pipeline_progress import _is_stage_end_message, _is_stage_start_message


class PipelineProgressMessageTests(unittest.TestCase):
    def test_discovery_stage_boundaries(self) -> None:
        self.assertTrue(_is_stage_start_message("Starting source discovery"))
        self.assertTrue(_is_stage_start_message("Starting source rediscovery"))
        self.assertTrue(_is_stage_end_message("Source discovery completed"))

    def test_intermediate_discovery_messages_do_not_end_stage(self) -> None:
        self.assertFalse(_is_stage_end_message("Candidate exploration summary"))
        self.assertFalse(_is_stage_end_message("LLM listing selection result"))
        self.assertFalse(_is_stage_end_message("LLM detail-pattern selection result"))

    def test_source_stage_boundaries(self) -> None:
        self.assertTrue(_is_stage_start_message("Starting source crawl"))
        self.assertTrue(_is_stage_end_message("Completed source processing"))
        self.assertFalse(_is_stage_end_message("Detail payloads collected"))
        self.assertFalse(_is_stage_end_message("Accepted cleaned payload"))


class CompactReporterCapture:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def log(
        self,
        *,
        stage: str,
        message: str,
        source: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        self.events.append(
            {
                "stage": stage,
                "message": message,
                "source": source,
                "details": details or {},
            }
        )


class DiscoveryLoggingTests(unittest.IsolatedAsyncioTestCase):
    async def test_discovery_emits_compact_milestone_logs(self) -> None:
        homepage_html = """
        <html><body>
          <a href="/recalls">Food product recalls</a>
          <a href="/about">About</a>
        </body></html>
        """
        listing_html = """
        <html><body>
          <a href="/recalls/alert/abc">Milk recall</a>
          <a href="/recalls/alert/def">Cheese recall</a>
        </body></html>
        """

        async def fake_fetch(_client: httpx.AsyncClient, url: str, **_kwargs: object) -> tuple[str, str]:
            if "/recalls" in url and "alert" not in url:
                return listing_html, url
            return homepage_html, url

        reporter = CompactReporterCapture()
        with (
            patch(
                "agents.fetchers.crawler.source_discovery.fetch_static_html",
                new=AsyncMock(side_effect=fake_fetch),
            ),
            patch(
                "agents.fetchers.crawler.source_discovery.fetch_browser_html",
                new=AsyncMock(side_effect=RuntimeError("browser unused")),
            ),
            patch(
                "agents.fetchers.crawler.source_discovery.chat_json",
                side_effect=[
                    {
                        "seed_urls": ["https://example.gov/recalls"],
                        "confidence": 0.9,
                        "reason": "listing",
                    },
                    {
                        "detail_page_keywords": ["/recalls/alert/"],
                        "blocked_paths": ["/about"],
                        "date_languages": ["en"],
                        "reason": "patterns",
                    },
                ],
            ),
        ):
            await discover_source_config(
                source_name="example",
                homepage_url="https://example.gov/",
                country_source="Example",
                client=AsyncMock(spec=httpx.AsyncClient),
                reporter=reporter,  # type: ignore[arg-type]
            )

        messages = [str(event["message"]) for event in reporter.events]
        self.assertEqual(
            messages,
            [
                "Starting source discovery",
                "Candidate exploration summary",
                "LLM listing selection result",
                "LLM detail-pattern selection result",
                "Source discovery completed",
            ],
        )
        self.assertTrue(all(event["stage"] == "discovery" for event in reporter.events))
        completed = reporter.events[-1]["details"]
        assert isinstance(completed, dict)
        self.assertIn("seed_urls", completed)
        self.assertIn("used_listing_fallback", completed)
        self.assertNotIn("html_excerpt", completed)


class CrawlLoggingTests(unittest.IsolatedAsyncioTestCase):
    async def test_crawl_logs_omit_html_and_full_payloads(self) -> None:
        source_config = ScraperSourceConfig(
            base_url="https://example.com",
            allowed_domains=["example.com"],
            seed_urls=["https://example.com/recalls"],
            max_depth=1,
            max_pages_per_run=1,
            hints=ScraperHints(detail_page_keywords=["/recalls/"]),
        )
        reporter = CompactReporterCapture()
        with (
            patch(
                "agents.fetchers.crawler.orchestrator.fetch_static_html",
                new=AsyncMock(
                    return_value=(
                        "<html><body><a href='/recalls/1'>One</a></body></html>",
                        "https://example.com/recalls",
                    )
                ),
            ),
            patch(
                "agents.fetchers.crawler.orchestrator.classify_page",
                return_value="detail",
            ),
            patch(
                "agents.fetchers.crawler.orchestrator.extract_detail_payload",
                return_value={
                    "source_url": "https://example.com/recalls",
                    "headings": ["Recall"],
                    "visible_text": "long text " * 50,
                    "published_date_candidates": ["2026-07-01"],
                },
            ),
            patch(
                "agents.fetchers.crawler.orchestrator.extract_internal_links",
                return_value=["https://example.com/recalls/1"],
            ),
        ):
            await crawl_source_pages(
                source_name="uk",
                source_config=source_config,
                client=AsyncMock(spec=httpx.AsyncClient),
                reporter=reporter,  # type: ignore[arg-type]
            )

        detail_blob = " ".join(str(event["details"]) for event in reporter.events)
        self.assertNotIn("html_excerpt", detail_blob)
        self.assertNotIn("extracted_payload", detail_blob)
        self.assertNotIn("visible_text", detail_blob)
        messages = [str(event["message"]) for event in reporter.events]
        self.assertIn("Starting crawl queue", messages)
        self.assertIn("Source crawl finished", messages)


if __name__ == "__main__":
    unittest.main()
