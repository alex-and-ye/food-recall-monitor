from __future__ import annotations

import json
from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class FoodRecallAlertStats(BaseModel):
    total_alerts: int
    top_5_hazard_types: list[tuple[str, int]]
    top_5_product_categories: list[tuple[str, int]]
    top_5_affected_regions: list[tuple[str, int]]
    alerts_last_7_days: int
    alerts_last_30_days: int

class FoodRecallAlertCreate(BaseModel):
    """Recall alert produced by the pipeline before database persistence."""

    api_source: str
    product_name: str
    product_category: str
    recall_reason: str
    summary: str
    recall_date: date
    risk_level: str
    hazard_type: str
    consumer_action: str
    source_url: str
    affected_regions: list[str] = Field(default_factory=list)

    def to_document(self) -> str:
        regions = ", ".join(self.affected_regions) if self.affected_regions else "unspecified"
        return "\n".join(
            [
                f"API source: {self.api_source}",
                f"Product: {self.product_name}",
                f"Category: {self.product_category}",
                f"Summary: {self.summary}",
                f"Reason: {self.recall_reason}",
                f"Hazard: {self.hazard_type}",
                f"Risk level: {self.risk_level}",
                f"Consumer action: {self.consumer_action}",
                f"Affected regions: {regions}",
            ]
        )


class FoodRecallAlert(FoodRecallAlertCreate):
    """Recall alert after the database assigns a stable identifier."""

    alert_id: str

    def get_id(self) -> str:
        return self.alert_id

    def to_metadata(self) -> dict[str, str | int | float | bool]:
        return {
            "alert_id": self.alert_id,
            "api_source": self.api_source,
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
        }

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

        return cls(
            alert_id=str(metadata["alert_id"]),
            api_source=str(metadata.get("api_source", "unknown")),
            product_name=str(metadata["product_name"]),
            product_category=str(metadata["product_category"]),
            recall_reason=str(metadata["recall_reason"]),
            summary=str(metadata["summary"]),
            recall_date=recall_date,
            risk_level=str(metadata["risk_level"]),
            hazard_type=str(metadata["hazard_type"]),
            consumer_action=str(metadata["consumer_action"]),
            source_url=str(metadata["source_url"]),
            affected_regions=affected_regions,
        )