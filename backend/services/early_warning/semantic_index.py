from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import chromadb
from chromadb.api.types import Metadata, Where
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

from models.early_warning_incident import EarlyWarningIncident
from models.food_recall_alert import FoodRecallAlert


@dataclass(frozen=True)
class SemanticNeighbor:
    record_id: str
    entity_type: str
    score: float


class SafetyEventSemanticIndex:
    """Derived, rebuildable semantic index for English-normalized safety events."""

    def __init__(
        self,
        host: str,
        port: int,
        *,
        collection_name: str = "safety_event_similarity_v1",
        model_name: str = "all-MiniLM-L6-v2",
    ) -> None:
        if model_name != "all-MiniLM-L6-v2":
            raise ValueError(
                "The bundled Chroma embedding function supports all-MiniLM-L6-v2 only"
            )
        self.model_name = model_name
        self.client = chromadb.HttpClient(host=host, port=port)
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=DefaultEmbeddingFunction(),
            metadata={
                "hnsw:space": "cosine",
                "embedding_model": model_name,
                "index_version": "1",
            },
        )

    def upsert_incident(self, incident: EarlyWarningIncident) -> None:
        self._upsert(
            record_id=incident.incident_id,
            entity_type="incident",
            document=_incident_document(incident),
        )

    def upsert_official_alert(self, alert: FoodRecallAlert) -> None:
        self._upsert(
            record_id=alert.alert_id,
            entity_type="official_alert",
            document=_official_document(alert),
        )

    def query_incidents(
        self,
        incident: EarlyWarningIncident,
        *,
        limit: int = 10,
    ) -> list[SemanticNeighbor]:
        if limit < 1:
            return []
        result = self.collection.query(
            query_texts=[_incident_document(incident)],
            n_results=limit + 1,
            where=cast(Where, {"entity_type": "incident"}),
            include=["distances", "metadatas"],
        )
        ids = _first_list(result.get("ids"))
        distances = _first_list(result.get("distances"))
        metadatas = _first_list(result.get("metadatas"))
        neighbors: list[SemanticNeighbor] = []
        for index, record_id in enumerate(ids):
            distance = _float_at(distances, index)
            metadata = metadatas[index] if index < len(metadatas) else {}
            entity_type = (
                str(metadata.get("entity_type", "incident"))
                if isinstance(metadata, dict)
                else "incident"
            )
            logical_id = (
                str(metadata.get("record_id", record_id))
                if isinstance(metadata, dict)
                else str(record_id)
            )
            if logical_id == incident.incident_id:
                continue
            neighbors.append(
                SemanticNeighbor(
                    record_id=logical_id,
                    entity_type=entity_type,
                    score=max(0.0, min(1.0, 1.0 - distance)),
                )
            )
            if len(neighbors) >= limit:
                break
        return neighbors

    def rebuild(
        self,
        *,
        incidents: list[EarlyWarningIncident],
        official_alerts: list[FoodRecallAlert],
    ) -> None:
        for incident in incidents:
            self.upsert_incident(incident)
        for alert in official_alerts:
            self.upsert_official_alert(alert)

    def _upsert(self, *, record_id: str, entity_type: str, document: str) -> None:
        metadata = cast(
            Metadata,
            {
                "record_id": record_id,
                "entity_type": entity_type,
                "embedding_model": self.model_name,
            },
        )
        self.collection.upsert(
            ids=[f"{entity_type}:{record_id}"],
            documents=[document],
            metadatas=[metadata],
        )


def _incident_document(incident: EarlyWarningIncident) -> str:
    return "\n".join(
        value
        for value in (
            f"Product: {incident.product_name}",
            f"Company: {incident.company_name}",
            f"Hazard: {incident.hazard_type}",
            f"Country: {incident.country}",
            f"Reason: {incident.incident_reason}",
            f"Summary: {incident.summary}",
        )
        if value.split(":", maxsplit=1)[1].strip()
    )


def _official_document(alert: FoodRecallAlert) -> str:
    return "\n".join(
        (
            f"Product: {alert.product_name}",
            f"Hazard: {alert.hazard_type}",
            f"Country: {alert.country_source}",
            f"Reason: {alert.recall_reason}",
            f"Summary: {alert.summary}",
        )
    )


def _first_list(value: Any) -> list[Any]:
    if not isinstance(value, list) or not value:
        return []
    first = value[0]
    return first if isinstance(first, list) else []


def _float_at(values: list[Any], index: int) -> float:
    if index >= len(values):
        return 1.0
    try:
        return float(values[index])
    except (TypeError, ValueError):
        return 1.0
