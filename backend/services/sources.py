from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from agents.fetchers.crawler.source_discovery import derive_base_url_and_domains, discover_source_config
from agents.fetchers.scraper_ingestion import SOURCE_REQUEST_HEADERS
from db.source_config_interface import ScraperSourceConfigDBInterface
from models.pipeline_progress import ProgressReporter
from models.scraper_config import ScraperHints, ScraperSourceConfig
from models.source_registry import SourceCreateRequest, SourceRegistryDocument

LOGGER = logging.getLogger(__name__)


class SourcesService:
    def __init__(self, source_db: ScraperSourceConfigDBInterface) -> None:
        self._source_db = source_db

    def list_sources(self) -> list[SourceRegistryDocument]:
        return self._source_db.list_sources()

    def get_source(self, source_name: str) -> SourceRegistryDocument | None:
        return self._source_db.get_source(source_name)

    def delete_source(self, source_name: str) -> bool:
        return self._source_db.delete_source(source_name)

    def upsert_document(self, document: SourceRegistryDocument) -> SourceRegistryDocument:
        return self._source_db.upsert_source(document)

    async def register_source(
        self,
        request: SourceCreateRequest,
        *,
        reporter: ProgressReporter | None = None,
    ) -> SourceRegistryDocument:
        existing = self._source_db.get_source(request.name)
        if existing is not None:
            raise ValueError(f"Source already exists: {request.name}")

        document = await self._run_discovery(
            source_name=request.name,
            homepage_url=request.homepage_url,
            country_source=request.country_source,
            reporter=reporter,
        )
        return self._source_db.upsert_source(document)

    async def rediscover_source(
        self,
        source_name: str,
        *,
        homepage_url: str | None = None,
        country_source: str | None = None,
        reporter: ProgressReporter | None = None,
    ) -> SourceRegistryDocument:
        existing = self._source_db.get_source(source_name)
        if existing is None and not homepage_url:
            raise KeyError(f"Unknown source: {source_name}")

        resolved_homepage = homepage_url or (existing.homepage_url if existing else "")
        resolved_country = country_source or (existing.country_source if existing else source_name)
        document = await self._run_discovery(
            source_name=source_name,
            homepage_url=resolved_homepage,
            country_source=resolved_country,
            reporter=reporter,
        )
        return self._source_db.upsert_source(document)

    def mark_stale(self, source_name: str, reason: str) -> SourceRegistryDocument | None:
        existing = self._source_db.get_source(source_name)
        if existing is None:
            return None
        updated = existing.touch(status="stale", reason=reason)
        return self._source_db.upsert_source(updated)

    async def _run_discovery(
        self,
        *,
        source_name: str,
        homepage_url: str,
        country_source: str | None,
        reporter: ProgressReporter | None,
    ) -> SourceRegistryDocument:
        async with httpx.AsyncClient(
            timeout=30.0,
            headers=SOURCE_REQUEST_HEADERS,
            follow_redirects=True,
        ) as client:
            try:
                return await discover_source_config(
                    source_name=source_name,
                    homepage_url=homepage_url,
                    country_source=country_source,
                    client=client,
                    reporter=reporter,
                )
            except Exception as exc:
                LOGGER.exception("Source discovery failed for %s", source_name)
                now = datetime.now(timezone.utc)
                try:
                    base_url, domains = derive_base_url_and_domains(homepage_url)
                except ValueError:
                    base_url, domains = homepage_url, ["invalid.local"]
                failed = SourceRegistryDocument(
                    source_name=source_name,
                    homepage_url=homepage_url,
                    country_source=(country_source or source_name),
                    config=ScraperSourceConfig(
                        base_url=base_url,
                        allowed_domains=domains or ["invalid.local"],
                        seed_urls=[homepage_url],
                        hints=ScraperHints(),
                    ),
                    discovery_status="failed",
                    discovery_reason=str(exc),
                    discovered_at=now,
                    updated_at=now,
                )
                self._source_db.upsert_source(failed)
                raise
