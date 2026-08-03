from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

from models.scraper_config import ScraperSourceConfig

class DiscoveryStatus(StrEnum):
    READY = "ready"
    FAILED = "failed"
    STALE = "stale"
    PENDING = "pending"

DISCOVERY_STATUSES: frozenset[str] = frozenset(DiscoveryStatus)

DISCOVERY_STATUSES_NEEDING_REFRESH: frozenset[str] = frozenset(
    {
        DiscoveryStatus.FAILED,
        DiscoveryStatus.STALE,
        DiscoveryStatus.PENDING,
    }
)

class SourceRegistryDocument(BaseModel):
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
        text = str(value).strip().lower()
        if not text:
            raise ValueError("source_name must be non-empty")
        return text

    @field_validator("homepage_url", mode="before")
    @classmethod
    def _normalize_homepage_url(cls, value: object) -> str:
        text = str(value).strip()
        if not text:
            raise ValueError("homepage_url must be non-empty")
        return text

    @field_validator("country_source", mode="before")
    @classmethod
    def _normalize_country_source(cls, value: object) -> str:
        text = str(value).strip()
        if not text:
            raise ValueError("country_source must be non-empty")
        return text

    def touch(self, *, status: DiscoveryStatus | None = None, reason: str | None = None) -> SourceRegistryDocument:
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
    name: str = Field(min_length=1)
    homepage_url: str = Field(min_length=1)
    country_source: str | None = None

    @field_validator("name", mode="before")
    @classmethod
    def _normalize_name(cls, value: object) -> str:
        return str(value).strip().lower()

    @field_validator("homepage_url", mode="before")
    @classmethod
    def _normalize_homepage(cls, value: object) -> str:
        return str(value).strip()

    @field_validator("country_source", mode="before")
    @classmethod
    def _normalize_country(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
