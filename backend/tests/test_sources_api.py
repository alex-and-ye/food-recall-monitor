from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from db.chroma_source_client import InMemoryScraperSourceConfigStore
from models.scraper_config import ScraperHints, ScraperSourceConfig
from models.source_registry import SourceCreateRequest, SourceRegistryDocument
from services.sources import SourcesService


def _ready_document(name: str = "demo") -> SourceRegistryDocument:
    now = datetime.now(timezone.utc)
    return SourceRegistryDocument(
        source_name=name,
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


class SourcesServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.store = InMemoryScraperSourceConfigStore()
        self.service = SourcesService(self.store)

    def test_list_get_and_delete(self) -> None:
        self.store.upsert_source(_ready_document())
        self.assertEqual(len(self.service.list_sources()), 1)
        self.assertEqual(self.service.get_source("demo").source_name, "demo")
        self.assertTrue(self.service.delete_source("demo"))
        self.assertIsNone(self.service.get_source("demo"))

    async def test_register_source_persists_discovery(self) -> None:
        discovered = _ready_document("canada")
        with patch(
            "services.sources.discover_source_config",
            new=AsyncMock(return_value=discovered),
        ):
            result = await self.service.register_source(
                SourceCreateRequest(
                    name="canada",
                    homepage_url="https://demo.example/",
                    country_source="Canada",
                )
            )
        self.assertEqual(result.source_name, "canada")
        self.assertEqual(self.store.get_source("canada").country_source, "Demo")

    async def test_register_source_conflict(self) -> None:
        self.store.upsert_source(_ready_document("canada"))
        with self.assertRaises(ValueError):
            await self.service.register_source(
                SourceCreateRequest(name="canada", homepage_url="https://demo.example/")
            )

    async def test_rediscover_source(self) -> None:
        self.store.upsert_source(_ready_document("demo"))
        rediscovered = _ready_document("demo")
        rediscovered = rediscovered.model_copy(
            update={
                "config": rediscovered.config.model_copy(
                    update={"seed_urls": ["https://demo.example/new-recalls"]}
                )
            }
        )
        with patch(
            "services.sources.discover_source_config",
            new=AsyncMock(return_value=rediscovered),
        ):
            result = await self.service.rediscover_source("demo")
        self.assertEqual(result.config.seed_urls, ["https://demo.example/new-recalls"])


if __name__ == "__main__":
    unittest.main()
