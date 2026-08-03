"""Manage scraper source registry documents and LLM-driven discovery.

Supports listing, registration, rediscovery, and stale marking for homepage
sources used by the official recall crawl pipeline.
"""

import logging
from datetime import datetime, timezone

import httpx

from agents.fetchers.crawler.source_discovery import derive_base_url_and_domains, discover_source_config
from agents.fetchers.scraper_ingestion import SOURCE_REQUEST_HEADERS
from constants import HTTP_CLIENT_TIMEOUT_SECONDS
from db.source_config_interface import ScraperSourceConfigDBInterface
from models.pipeline_progress import ProgressReporter
from models.scraper_config import ScraperHints, ScraperSourceConfig
from models.source_registry import DiscoveryStatus, SourceCreateRequest, SourceRegistryDocument

LOGGER = logging.getLogger(__name__)  # Module logger for discovery failures.


class SourcesService:
    """CRUD and discovery operations for scraper source registry entries."""

    def __init__(self, source_db: ScraperSourceConfigDBInterface) -> None:
        """Initialize with a source configuration database.

        Args:
            source_db: Backend used to persist source registry documents.
        """
        self._source_db = source_db

    def list_sources(self) -> list[SourceRegistryDocument]:
        """Return all registered sources.

        Returns:
            List of source registry documents.
        """
        return self._source_db.list_sources()

    def get_source(self, source_name: str) -> SourceRegistryDocument | None:
        """Fetch one source by name.

        Args:
            source_name: Unique source identifier.

        Returns:
            Matching document, or None if unknown.
        """
        return self._source_db.get_source(source_name)

    def delete_source(self, source_name: str) -> bool:
        """Delete a source by name.

        Args:
            source_name: Unique source identifier.

        Returns:
            True if a document was deleted.
        """
        return self._source_db.delete_source(source_name)

    def upsert_document(self, document: SourceRegistryDocument) -> SourceRegistryDocument:
        """Insert or replace a source registry document.

        Args:
            document: Full source document to persist.

        Returns:
            Persisted document returned by the database.
        """
        return self._source_db.upsert_source(document)

    async def register_source(
        self,
        request: SourceCreateRequest,
        *,
        reporter: ProgressReporter | None = None,
    ) -> SourceRegistryDocument:
        """Discover and register a new homepage source.

        Args:
            request: Create request with name, homepage URL, and country.
            reporter: Optional progress reporter for discovery steps.

        Returns:
            Newly discovered and upserted source document.

        Raises:
            ValueError: If a source with the same name already exists.
            Exception: Propagates discovery failures after persisting FAILED status.
        """
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
        """Re-run discovery for an existing or explicitly provided homepage.

        Args:
            source_name: Source name to rediscover.
            homepage_url: Optional override homepage; required if source is unknown.
            country_source: Optional country override.
            reporter: Optional progress reporter for discovery steps.

        Returns:
            Upserted rediscovered source document.

        Raises:
            KeyError: If the source is unknown and no homepage_url is given.
            Exception: Propagates discovery failures after persisting FAILED status.
        """
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
        """Mark an existing source as stale with a reason.

        Args:
            source_name: Source to update.
            reason: Human-readable staleness reason.

        Returns:
            Updated document, or None if the source does not exist.
        """
        existing = self._source_db.get_source(source_name)
        if existing is None:
            return None
        updated = existing.touch(status=DiscoveryStatus.STALE, reason=reason)
        return self._source_db.upsert_source(updated)

    async def _run_discovery(
        self,
        *,
        source_name: str,
        homepage_url: str,
        country_source: str | None,
        reporter: ProgressReporter | None,
    ) -> SourceRegistryDocument:
        """Run LLM/heuristic discovery and persist FAILED docs on error.

        Args:
            source_name: Unique source name.
            homepage_url: Homepage used as the discovery seed.
            country_source: Optional country label for the source.
            reporter: Optional progress reporter.

        Returns:
            Successfully discovered SourceRegistryDocument.

        Raises:
            Exception: Re-raises discovery errors after upserting a FAILED document.
        """
        async with httpx.AsyncClient(
            timeout=HTTP_CLIENT_TIMEOUT_SECONDS,
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
                    discovery_status=DiscoveryStatus.FAILED,
                    discovery_reason=str(exc),
                    discovered_at=now,
                    updated_at=now,
                )
                self._source_db.upsert_source(failed)
                raise
