from __future__ import annotations

import json
from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

class WebSource(StrEnum):
    UK = "uk"
    GERMANY = "germany"
    FRANCE = "france"

class CountrySource(StrEnum):
    UK = "UK"
    GERMANY = "Germany"
    FRANCE = "France"

WEB_SOURCE_TO_COUNTRY_SOURCE: dict[str, str] = {
    WebSource.UK: CountrySource.UK,
    WebSource.GERMANY: CountrySource.GERMANY,
    WebSource.FRANCE: CountrySource.FRANCE,
}

COUNTRY_SOURCES: frozenset[str] = frozenset(WEB_SOURCE_TO_COUNTRY_SOURCE.values())
WEB_SOURCE_KEYS: frozenset[str] = frozenset(WEB_SOURCE_TO_COUNTRY_SOURCE.keys())

# Legacy Chroma metadata key accepted when reading older alert records.
LEGACY_WEB_SOURCE_METADATA_KEY = "api_source"
WEB_SOURCE_METADATA_KEY = "web_source"

_country_source_lookup: Any | None = None


def set_country_source_lookup(lookup: Any) -> None:
    global _country_source_lookup
    _country_source_lookup = lookup


def web_source_to_country_source(web_source: str) -> str:
    key = web_source.strip().lower()
    if _country_source_lookup is not None:
        try:
            resolved = _country_source_lookup(key)
        except Exception:
            resolved = None
        if isinstance(resolved, str) and resolved.strip():
            return resolved.strip()
    return WEB_SOURCE_TO_COUNTRY_SOURCE.get(key, web_source)

class FoodRecallAlertStats(BaseModel):
    total_alerts: int
    top_5_hazard_types: list[tuple[str, int]]
    top_5_product_categories: list[tuple[str, int]]
    top_5_affected_regions: list[tuple[str, int]]
    alerts_last_7_days: int
    alerts_last_30_days: int

class FoodRecallAlertsVersion(BaseModel):
    count: int
    fingerprint: str

class FoodRecallAlertCreate(BaseModel):
    """Recall alert produced by the pipeline before database persistence."""

    web_source: str
    country_source: str
    product_name: str
    product_category: str
    recall_reason: str
    summary: str
    recall_date: date
    risk_level: str
    hazard_type: str
    consumer_action: str
    source_url: str
    batch_id: str = ""
    affected_regions: list[str] = Field(default_factory=list)
    latitude: float = Field(default=0.0, ge=-90.0, le=90.0)
    longitude: float = Field(default=0.0, ge=-180.0, le=180.0)

    def to_document(self) -> str:
        regions = ", ".join(self.affected_regions) if self.affected_regions else "unspecified"
        batch_id = self.batch_id.strip() or "unspecified"
        return "\n".join(
            [
                f"Web source: {self.web_source}",
                f"Country source: {self.country_source}",
                f"Product: {self.product_name}",
                f"Category: {self.product_category}",
                f"Batch ID: {batch_id}",
                f"Summary: {self.summary}",
                f"Reason: {self.recall_reason}",
                f"Hazard: {self.hazard_type}",
                f"Risk level: {self.risk_level}",
                f"Consumer action: {self.consumer_action}",
                f"Affected regions: {regions}",
                f"Latitude: {self.latitude}",
                f"Longitude: {self.longitude}",
            ]
        )

class FoodRecallAlert(FoodRecallAlertCreate):
    """Recall alert after the database assigns a stable identifier."""

    alert_id: str

    def get_id(self) -> str:
        return self.alert_id

    def search_values(self) -> list[str]:
        return [
            self.web_source,
            self.country_source,
            self.product_name,
            self.product_category,
            self.batch_id,
            self.recall_reason,
            self.summary,
            self.recall_date.isoformat(),
            self.risk_level,
            self.hazard_type,
            self.consumer_action,
            self.source_url,
            *self.affected_regions,
        ]

    def matches_search(self, keyword: str) -> bool:
        search_term = keyword.strip().lower()
        if not search_term:
            return True

        searchable_text = " ".join(
            value for value in self.search_values() if value
        ).lower()
        return search_term in searchable_text

    def to_metadata(self) -> dict[str, str | int | float | bool]:
        metadata: dict[str, str | int | float | bool] = {
            "alert_id": self.alert_id,
            "web_source": self.web_source,
            "country_source": self.country_source,
            "product_name": self.product_name,
            "product_category": self.product_category,
            "recall_reason": self.recall_reason,
            "summary": self.summary,
            "recall_date": self.recall_date.isoformat(),
            "risk_level": self.risk_level,
            "hazard_type": self.hazard_type,
            "consumer_action": self.consumer_action,
            "source_url": self.source_url,
            "affected_regions": json.dumps(self.affected_regions),
            "latitude": float(self.latitude),
            "longitude": float(self.longitude),
        }
        # Chroma rejects empty string metadata values.
        batch_id = self.batch_id.strip()
        if batch_id:
            metadata["batch_id"] = batch_id
        return metadata

    @classmethod
    def from_metadata(cls, metadata: dict[str, Any]) -> FoodRecallAlert:
        regions_raw = metadata.get("affected_regions", "[]")
        if isinstance(regions_raw, list):
            affected_regions = regions_raw
        elif isinstance(regions_raw, str):
            affected_regions = json.loads(regions_raw) if regions_raw else []
        else:
            affected_regions = []

        recall_date_raw = metadata["recall_date"]
        if isinstance(recall_date_raw, date):
            recall_date = recall_date_raw
        else:
            recall_date = date.fromisoformat(str(recall_date_raw))

        # Prefer web_source; accept legacy key for older Chroma records.
        web_source = str(
            metadata.get(WEB_SOURCE_METADATA_KEY)
            or metadata.get(LEGACY_WEB_SOURCE_METADATA_KEY)
            or "unknown"
        )
        country_source_raw = metadata.get("country_source")
        country_source = (
            str(country_source_raw)
            if country_source_raw
            else web_source_to_country_source(web_source)
        )

        return cls(
            alert_id=str(metadata["alert_id"]),
            web_source=web_source,
            country_source=country_source,
            product_name=str(metadata["product_name"]),
            product_category=str(metadata["product_category"]),
            recall_reason=str(metadata["recall_reason"]),
            summary=str(metadata["summary"]),
            recall_date=recall_date,
            risk_level=str(metadata["risk_level"]),
            hazard_type=str(metadata["hazard_type"]),
            consumer_action=str(metadata["consumer_action"]),
            source_url=str(metadata["source_url"]),
            batch_id=str(metadata.get("batch_id", "") or "").strip(),
            affected_regions=affected_regions,
            latitude=_parse_coordinate(metadata.get("latitude"), default=0.0),
            longitude=_parse_coordinate(metadata.get("longitude"), default=0.0),
        )

def _parse_coordinate(value: Any, *, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
