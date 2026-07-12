from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import httpx

from agents.fetchers.crawler.source_discovery import (
    derive_base_url_and_domains,
    extract_link_candidates,
    rank_candidates,
    score_recall_candidate,
    discover_source_config,
)
from db.chroma_source_client import InMemoryScraperSourceConfigStore
from models.scraper_config import ScraperHints, ScraperSourceConfig
from models.source_registry import SourceRegistryDocument
from services.source_bootstrap import ensure_bootstrap_sources


class SourceDiscoveryUnitTests(unittest.TestCase):
    def test_derive_base_url_and_domains(self) -> None:
        base_url, domains = derive_base_url_and_domains("https://www.Example.gov/path")
        self.assertEqual(base_url, "https://www.example.gov")
        self.assertEqual(domains, ["www.example.gov", "example.gov"])

    def test_score_recall_candidate_prefers_recall_paths(self) -> None:
        high = score_recall_candidate("https://example.gov/food-alerts/recall", "Product recalls")
        low = score_recall_candidate("https://example.gov/about/contact", "Contact us")
        self.assertGreater(high, low)

    def test_extract_and_rank_candidates(self) -> None:
        html = """
        <html><body>
          <a href="/about">About</a>
          <a href="/recalls">Food recalls</a>
          <a href="/news-alerts/alert/1">Alert one</a>
        </body></html>
        """
        candidates = extract_link_candidates(
            current_url="https://example.gov/",
            html=html,
            allowed_domains=["example.gov"],
        )
        ranked = rank_candidates(candidates, limit=2)
        self.assertEqual(len(ranked), 2)
        ranked_urls = " ".join(item.url for item in ranked)
        self.assertTrue("/recalls" in ranked_urls or "/news-alerts/alert/" in ranked_urls)
        self.assertNotIn("/about", ranked_urls)


class SourceDiscoveryAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_discover_source_config_builds_config_from_llm(self) -> None:
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
          <a href="/faq">FAQ</a>
        </body></html>
        """

        async def fake_fetch(_client: httpx.AsyncClient, url: str, **_kwargs: object) -> tuple[str, str]:
            if "/recalls" in url and "alert" not in url:
                return listing_html, url
            return homepage_html, url

        with (
            patch(
                "agents.fetchers.crawler.source_discovery.fetch_static_html",
                new=AsyncMock(side_effect=fake_fetch),
            ),
            patch(
                "agents.fetchers.crawler.source_discovery.fetch_browser_html",
                new=AsyncMock(side_effect=RuntimeError("browser should not be required")),
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
                        "blocked_paths": ["/faq", "/about"],
                        "date_languages": ["en"],
                        "reason": "patterns",
                    },
                ],
            ),
        ):
            document = await discover_source_config(
                source_name="example",
                homepage_url="https://example.gov/",
                country_source="Example",
                client=AsyncMock(spec=httpx.AsyncClient),
            )

        self.assertEqual(document.source_name, "example")
        self.assertEqual(document.country_source, "Example")
        self.assertEqual(document.discovery_status, "ready")
        self.assertEqual(document.config.seed_urls, ["https://example.gov/recalls"])
        self.assertEqual(document.config.hints.detail_page_keywords, ["/recalls/alert/"])
        self.assertIn("/faq", document.config.hints.blocked_paths)


class SourceRegistryStoreTests(unittest.TestCase):
    def test_in_memory_store_roundtrip(self) -> None:
        store = InMemoryScraperSourceConfigStore()
        now = datetime.now(timezone.utc)
        document = SourceRegistryDocument(
            source_name="demo",
            homepage_url="https://demo.example/",
            country_source="Demo",
            config=ScraperSourceConfig(
                base_url="https://demo.example",
                allowed_domains=["demo.example"],
                seed_urls=["https://demo.example/recalls"],
                hints=ScraperHints(detail_page_keywords=["/recalls/"]),
            ),
            discovery_status="ready",
            discovered_at=now,
            updated_at=now,
        )
        store.upsert_source(document)
        loaded = store.get_source("demo")
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.config.seed_urls, ["https://demo.example/recalls"])
        self.assertEqual(store.list_source_names(), ["demo"])
        self.assertTrue(store.delete_source("demo"))
        self.assertIsNone(store.get_source("demo"))

    def test_bootstrap_seeds_empty_store(self) -> None:
        store = InMemoryScraperSourceConfigStore()
        inserted = ensure_bootstrap_sources(store)
        self.assertEqual(inserted, 3)
        self.assertEqual(sorted(store.list_source_names()), ["france", "germany", "uk"])
        self.assertEqual(ensure_bootstrap_sources(store), 0)
        uk = store.get_source("uk")
        self.assertIsNotNone(uk)
        assert uk is not None
        self.assertEqual(uk.country_source, "UK")
        self.assertEqual(uk.homepage_url, "https://alerts.food.gov.uk/news-alerts")
        self.assertEqual(uk.discovery_status, "pending")
        self.assertEqual(uk.config.seed_urls, ["https://alerts.food.gov.uk/news-alerts"])


if __name__ == "__main__":
    unittest.main()
