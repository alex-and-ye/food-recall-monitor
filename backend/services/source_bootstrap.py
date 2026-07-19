from __future__ import annotations

from datetime import datetime, timezone

from agents.fetchers.crawler.source_discovery import derive_base_url_and_domains
from config.sources import BOOTSTRAP_SCRAPER_SOURCES
from db.source_config_interface import ScraperSourceConfigDBInterface
from models.food_recall_alert import WEB_SOURCE_TO_COUNTRY_SOURCE
from models.scraper_config import ScraperHints, ScraperSourceConfig
from models.source_registry import DiscoveryStatus, SourceRegistryDocument


def ensure_bootstrap_sources(source_db: ScraperSourceConfigDBInterface) -> int:
    """Seed pending homepage-only sources when the registry is empty. Returns inserted count."""
    if source_db.count_sources() > 0:
        return 0

    now = datetime.now(timezone.utc)
    inserted = 0
    for source_name, homepage_url in BOOTSTRAP_SCRAPER_SOURCES.items():
        base_url, allowed_domains = derive_base_url_and_domains(homepage_url)
        country_source = WEB_SOURCE_TO_COUNTRY_SOURCE.get(source_name, source_name.title())
        # Placeholder config until LLM discovery runs (status=pending triggers it).
        config = ScraperSourceConfig(
            base_url=base_url,
            allowed_domains=allowed_domains,
            seed_urls=[homepage_url],
            hints=ScraperHints(),
        )
        document = SourceRegistryDocument(
            source_name=source_name,
            homepage_url=homepage_url,
            country_source=country_source,
            config=config,
            discovery_status=DiscoveryStatus.PENDING,
            discovery_reason="bootstrapped homepage only; awaiting LLM discovery",
            discovered_at=now,
            updated_at=now,
        )
        source_db.upsert_source(document)
        inserted += 1
    return inserted
