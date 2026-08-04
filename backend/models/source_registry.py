"""Source registry models for configured official scrape targets.

Tracks each source's scraper config, discovery status, and API create
request shape for adding new sources.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

from models.scraper_config import ScraperSourceConfig

class DiscoveryStatus(StrEnum):
    """Lifecycle status of automated source-config discovery."""

    READY = "ready"
    FAILED = "failed"
    STALE = "stale"
    PENDING = "pending"

# All valid discovery-status string values.
DISCOVERY_STATUSES: frozenset[str] = frozenset(DiscoveryStatus)

# Statuses that indicate discovery should be re-run.
DISCOVERY_STATUSES_NEEDING_REFRESH: frozenset[str] = frozenset(
    {
        DiscoveryStatus.FAILED,
        DiscoveryStatus.STALE,
        DiscoveryStatus.PENDING,
    }
)

class SourceRegistryDocument(BaseModel):
    """Persisted registry entry for one official recall source."""

    source_name: str
    homepage_url: str
    country_source: str
    config: ScraperSourceConfig
    discovery_status: DiscoveryStatus = DiscoveryStatus.READY
    discovery_reason: str = ""
    discovered_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("source_name", mode="before")
    @classmethod
    def _normalize_source_name(cls, value: object) -> str:
        """Lowercase and strip the source name; reject empty values."""
        text = str(value).strip().lower()
        if not text:
            raise ValueError("source_name must be non-empty")
        return text

    @field_validator("homepage_url", mode="before")
    @classmethod
    def _normalize_homepage_url(cls, value: object) -> str:
        """Strip the homepage URL; reject empty values."""
        text = str(value).strip()
        if not text:
            raise ValueError("homepage_url must be non-empty")
        return text

    @field_validator("country_source", mode="before")
    @classmethod
    def _normalize_country_source(cls, value: object) -> str:
        """Strip the country source label; reject empty values."""
        text = str(value).strip()
        if not text:
            raise ValueError("country_source must be non-empty")
        return text

    def touch(self, *, status: DiscoveryStatus | None = None, reason: str | None = None) -> SourceRegistryDocument:
        """Return a copy with updated timestamps and optional discovery fields.

        Args:
            status: New discovery status; keeps current when omitted.
            reason: New discovery reason; keeps current when omitted.

        Returns:
            Updated ``SourceRegistryDocument`` with ``updated_at`` set to now.
        """
        now = datetime.now(timezone.utc)
        return self.model_copy(
            update={
                "discovery_status": status or self.discovery_status,
                "discovery_reason": self.discovery_reason if reason is None else reason,
                "updated_at": now,
                "discovered_at": self.discovered_at or now,
            }
        )

class SourceCreateRequest(BaseModel):
    """API payload for registering a new official source by homepage URL."""

    name: str = Field(min_length=1)
    homepage_url: str = Field(min_length=1)
    country_source: str | None = None

    @field_validator("name", mode="before")
    @classmethod
    def _normalize_name(cls, value: object) -> str:
        """Lowercase and strip the requested source name."""
        return str(value).strip().lower()

    @field_validator("homepage_url", mode="before")
    @classmethod
    def _normalize_homepage(cls, value: object) -> str:
        """Strip the requested homepage URL."""
        return str(value).strip()

    @field_validator("country_source", mode="before")
    @classmethod
    def _normalize_country(cls, value: object) -> str | None:
        """Strip optional country source; treat empty as unset."""
        if value is None:
            return None
        text = str(value).strip()
        return text or None
