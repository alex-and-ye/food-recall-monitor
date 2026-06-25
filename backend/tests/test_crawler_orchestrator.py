import unittest
from unittest.mock import AsyncMock, patch

import httpx

from agents.fetchers.crawler.orchestrator import crawl_source_pages
from models.scraper_config import ScraperHints, ScraperSourceConfig


class CrawlerOrchestratorTests(unittest.IsolatedAsyncioTestCase):
    async def test_orchestrator_respects_page_cap_and_collects_details(self) -> None:
        source_config = ScraperSourceConfig(
            base_url="https://example.com",
            allowed_domains=["example.com"],
            seed_urls=["https://example.com/recalls"],
            max_depth=1,
            max_pages_per_run=2,
            hints=ScraperHints(detail_page_keywords=["/recalls/"], blocked_paths=["/blocked"]),
        )

        with (
            patch(
                "agents.fetchers.crawler.orchestrator.fetch_static_html",
                new=AsyncMock(return_value=("<html><title>Recall</title><body>Recall risk text.</body></html>", "https://example.com/recalls/1")),
            ),
            patch(
                "agents.fetchers.crawler.orchestrator.classify_page",
                side_effect=["detail", "irrelevant"],
            ),
            patch(
                "agents.fetchers.crawler.orchestrator.extract_internal_links",
                return_value=["https://example.com/recalls/2"],
            ),
        ):
            pages = await crawl_source_pages(
                source_name="uk",
                source_config=source_config,
                client=AsyncMock(spec=httpx.AsyncClient),
            )

        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0]["source_url"], "https://example.com/recalls/1")

    async def test_orchestrator_falls_back_to_browser_on_static_403(self) -> None:
        source_config = ScraperSourceConfig(
            base_url="https://example.com",
            allowed_domains=["example.com"],
            seed_urls=["https://example.com/recalls"],
            max_depth=0,
            max_pages_per_run=1,
            hints=ScraperHints(detail_page_keywords=["/recalls/"]),
        )
        with (
            patch(
                "agents.fetchers.crawler.orchestrator.fetch_static_html",
                new=AsyncMock(
                    side_effect=httpx.HTTPStatusError(
                        "403",
                        request=AsyncMock(),
                        response=AsyncMock(),
                    )
                ),
            ),
            patch(
                "agents.fetchers.crawler.orchestrator.fetch_browser_html",
                new=AsyncMock(
                    return_value=(
                        "<html><title>Recall</title><body>Recall risk text.</body></html>",
                        "https://example.com/recalls/1",
                    )
                ),
            ) as browser_fetch,
            patch(
                "agents.fetchers.crawler.orchestrator.classify_page",
                return_value="detail",
            ),
        ):
            pages = await crawl_source_pages(
                source_name="us",
                source_config=source_config,
                client=AsyncMock(spec=httpx.AsyncClient),
            )

        browser_fetch.assert_awaited_once()
        self.assertEqual(len(pages), 1)


if __name__ == "__main__":
    unittest.main()
