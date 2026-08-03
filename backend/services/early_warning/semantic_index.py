"""Chroma-backed semantic similarity index for safety events.

Embeds English-normalized incident and official-alert documents for near-
duplicate detection. The collection is derived and rebuildable.
"""

from dataclasses import dataclass
from typing import Any, cast

import chromadb
from chromadb.api.types import Metadata, Where
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

from models.early_warning_incident import EarlyWarningIncident
from models.food_recall_alert import FoodRecallAlert


@dataclass(frozen=True)
class SemanticNeighbor:
    """A similar record retrieved from the semantic index.

    Attributes:
        record_id: Logical incident or alert identifier.
        entity_type: ``incident`` or ``official_alert``.
        score: Cosine similarity in ``[0, 1]``.
    """

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
        """Connect to Chroma and ensure the similarity collection exists.

        Args:
            host: Chroma HTTP host.
            port: Chroma HTTP port.
            collection_name: Target collection name.
            model_name: Embedding model; only all-MiniLM-L6-v2 is supported.

        Raises:
            ValueError: If ``model_name`` is unsupported.
        """
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
        """Index or refresh an early-warning incident document.

        Args:
            incident: Incident to embed and upsert.
        """
        self._upsert(
            record_id=incident.incident_id,
            entity_type="incident",
            document=_incident_document(incident),
        )

    def upsert_official_alert(self, alert: FoodRecallAlert) -> None:
        """Index or refresh an official recall alert document.

        Args:
            alert: Official alert to embed and upsert.
        """
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
        """Find nearest neighbor incidents by embedding similarity.

        Args:
            incident: Query incident whose document is embedded.
            limit: Maximum neighbors to return (excluding self).

        Returns:
            Similar incidents ordered by descending similarity score.
        """
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
        """Re-upsert all provided incidents and official alerts.

        Args:
            incidents: Early-warning incidents to index.
            official_alerts: Official alerts to index.
        """
        for incident in incidents:
            self.upsert_incident(incident)
        for alert in official_alerts:
            self.upsert_official_alert(alert)

    def _upsert(self, *, record_id: str, entity_type: str, document: str) -> None:
        """Upsert one document into the Chroma collection.

        Args:
            record_id: Logical record identifier.
            entity_type: Entity type tag stored in metadata.
            document: Text document to embed.
        """
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
    """Build an embedding document from incident fields.

    Args:
        incident: Source incident.

    Returns:
        Newline-joined labeled fields, omitting empty values.
    """
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
    """Build an embedding document from an official alert.

    Args:
        alert: Source official recall alert.

    Returns:
        Newline-joined labeled fields for embedding.
    """
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
    """Unwrap Chroma's nested list query result shape.

    Args:
        value: Raw ``ids``/``distances``/``metadatas`` field.

    Returns:
        Inner list for the first query, or empty list.
    """
    if not isinstance(value, list) or not value:
        return []
    first = value[0]
    return first if isinstance(first, list) else []


def _float_at(values: list[Any], index: int) -> float:
    """Safely read a float distance at ``index``.

    Args:
        values: Distance list from a Chroma query.
        index: Index to read.

    Returns:
        Parsed float, or 1.0 (max distance) when missing/invalid.
    """
    if index >= len(values):
        return 1.0
    try:
        return float(values[index])
    except (TypeError, ValueError):
        return 1.0
