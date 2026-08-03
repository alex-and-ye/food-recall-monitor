from __future__ import annotations

import hashlib
from datetime import date
from typing import List, Optional, cast
from uuid import uuid4

import chromadb
from chromadb.api.types import Metadata, Where

from db.interface import FoodRecallAlertsDBInterface
from models.food_recall_alert import FoodRecallAlert, FoodRecallAlertCreate, FoodRecallAlertsVersion
from models.sort_options import SortBy

class FoodRecallAlertsChromaClient(FoodRecallAlertsDBInterface):
    COLLECTION_NAME = "food_recall_alerts_collection"

    def __init__(self, host: str, port: int) -> None:
        self.client = chromadb.HttpClient(host=host, port=port)
        self.collection = self.client.get_or_create_collection(
            name=FoodRecallAlertsChromaClient.COLLECTION_NAME
        )

    def save_alerts(self, alerts: List[FoodRecallAlertCreate]) -> List[FoodRecallAlert]:
        if not alerts:
            return []

        incoming_keys = [self._build_dedupe_key(alert) for alert in alerts]
        existing_keys = self._get_existing_dedupe_keys(incoming_keys)
        existing_by_url = self._get_existing_alerts_by_source_url(
            [alert.source_url for alert in alerts]
        )
        seen_keys: set[str] = set()
        seen_urls: set[str] = set()
        new_alerts: list[FoodRecallAlert] = []
        updated_alerts: list[FoodRecallAlert] = []

        for alert, dedupe_key in zip(alerts, incoming_keys, strict=True):
            if alert.source_url in seen_urls:
                continue
            seen_urls.add(alert.source_url)

            existing = existing_by_url.get(alert.source_url)
            if existing is not None:
                existing_id, existing_key = existing
                if existing_key != dedupe_key:
                    updated_alerts.append(
                        FoodRecallAlert(
                            alert_id=existing_id,
                            **alert.model_dump(),
                        )
                    )
                continue

            if dedupe_key in existing_keys or dedupe_key in seen_keys:
                continue

            seen_keys.add(dedupe_key)
            new_alerts.append(
                FoodRecallAlert(
                    alert_id=str(uuid4()),
                    **alert.model_dump(),
                )
            )

        if updated_alerts:
            self.collection.update(
                ids=[alert.get_id() for alert in updated_alerts],
                documents=[alert.to_document() for alert in updated_alerts],
                metadatas=[
                    cast(Metadata, self._build_metadata(alert))
                    for alert in updated_alerts
                ],
            )

        if new_alerts:
            self.collection.add(
                ids=[alert.get_id() for alert in new_alerts],
                documents=[alert.to_document() for alert in new_alerts],
                metadatas=[
                    cast(Metadata, self._build_metadata(alert))
                    for alert in new_alerts
                ],
            )

        # Return inserts and content updates so callers can notify the UI.
        return [*new_alerts, *updated_alerts]

    def update_alert_coordinates(self, alert_id: str, latitude: float, longitude: float) -> bool:
        existing = self.get_alert_by_id(alert_id)
        if existing is None:
            return False

        updated = existing.model_copy(
            update={
                "latitude": latitude,
                "longitude": longitude,
            }
        )
        self.collection.update(
            ids=[alert_id],
            documents=[updated.to_document()],
            metadatas=[cast(Metadata, self._build_metadata(updated))],
        )
        return True

    def _get_existing_dedupe_keys(self, dedupe_keys: List[str]) -> set[str]:
        if not dedupe_keys:
            return set()

        records = self.collection.get(
            where=cast(Where, {"dedupe_key": {"$in": dedupe_keys}}),
            include=["metadatas"],
        )
        metadatas = records.get("metadatas") or []

        return {
            str(metadata["dedupe_key"])
            for metadata in metadatas
            if metadata is not None and metadata.get("dedupe_key")
        }

    def _get_existing_alerts_by_source_url(
        self,
        source_urls: List[str],
    ) -> dict[str, tuple[str, str]]:
        if not source_urls:
            return {}

        records = self.collection.get(
            where=cast(Where, {"source_url": {"$in": list(dict.fromkeys(source_urls))}}),
            include=["metadatas"],
        )
        ids = records.get("ids") or []
        metadatas = records.get("metadatas") or []
        existing: dict[str, tuple[str, str]] = {}
        for record_id, metadata in zip(ids, metadatas, strict=False):
            if metadata is None or not metadata.get("source_url"):
                continue
            existing[str(metadata["source_url"])] = (
                str(record_id),
                str(metadata.get("dedupe_key", "")),
            )
        return existing

    def _build_metadata(self, alert: FoodRecallAlert) -> dict[str, str | int | float | bool]:
        metadata = alert.to_metadata()
        metadata["dedupe_key"] = self._build_dedupe_key(alert)
        return metadata

    @staticmethod
    def _build_dedupe_key(alert: FoodRecallAlertCreate) -> str:
        raw_key = "\0".join(
            [
                alert.product_name,
                alert.recall_date.isoformat(),
                alert.source_url,
            ]
        )
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def get_alerts_version(self) -> FoodRecallAlertsVersion:
        results = self.collection.get(include=[])
        ids = results.get("ids") or []
        sorted_ids = sorted(ids)
        fingerprint = hashlib.sha256(",".join(sorted_ids).encode("utf-8")).hexdigest()

        return FoodRecallAlertsVersion(
            count=len(sorted_ids),
            fingerprint=fingerprint,
        )

    def get_alerts(self) -> List[FoodRecallAlert]:
        results = self.collection.get(include=["metadatas"])
        metadatas = results.get("metadatas")
        if not metadatas:
            return []
        
        parsed_alerts = []
        for metadata in metadatas:
            if metadata is not None:
                safe_metadata = dict(metadata)
                parsed_alerts.append(FoodRecallAlert.from_metadata(safe_metadata))
                
        parsed_alerts.sort(key=lambda x: x.recall_date, reverse=True)
        
        return parsed_alerts

    def search_alerts(
        self,
        search: str | None = None,
        risk_level: str | None = None,
        country_source: str | None = None,
        recall_date: date | None = None,
        sort_by: str | None = None,
    ) -> List[FoodRecallAlert]:
        alerts = self.get_alerts()

        if recall_date:
            alerts = [alert for alert in alerts if alert.recall_date == recall_date]

        if risk_level:
            alerts = [alert for alert in alerts if alert.risk_level == risk_level]

        if country_source:
            alerts = [alert for alert in alerts if alert.country_source == country_source]

        if search and search.strip():
            alerts = [alert for alert in alerts if alert.matches_search(search)]

        if sort_by == SortBy.OLDEST:
            alerts.sort(key=lambda alert: alert.recall_date)
        elif sort_by == SortBy.LATEST:
            alerts.sort(key=lambda alert: alert.recall_date, reverse=True)

        return alerts

    def get_alert_by_id(self, alert_id: str) -> Optional[FoodRecallAlert]:
        results = self.collection.get(ids=[alert_id], include=["metadatas"])
        metadatas = results.get("metadatas") or []
        if not metadatas or metadatas[0] is None:
            return None

        return FoodRecallAlert.from_metadata(dict(metadatas[0]))
