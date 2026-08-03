"""ChromaDB and in-memory stores for early-warning incidents.

Implements EarlyWarningIncidentsDBInterface against a remote Chroma
collection, plus a deterministic in-memory test double and legacy aliases.
"""

from collections.abc import Iterable
from typing import cast

import chromadb
from chromadb.api.types import Metadata

from db.early_warning_interface import EarlyWarningIncidentsDBInterface
from models.early_warning_incident import (
    EarlyWarningIncident,
    IncidentType,
    SourceKind,
    VerificationStatus,
)

class EarlyWarningIncidentsChromaClient(EarlyWarningIncidentsDBInterface):
    """Chroma-backed store for early-warning incidents."""

    # Chroma collection name for early-warning incidents
    COLLECTION_NAME = "early_warning_incidents_collection"

    def __init__(self, host: str, port: int) -> None:
        """Connect to Chroma and ensure the incidents collection exists.

        Args:
            host: Chroma HTTP host.
            port: Chroma HTTP port.
        """
        self.client = chromadb.HttpClient(host=host, port=port)
        self.collection = self.client.get_or_create_collection(name=self.COLLECTION_NAME)

    def list_incidents(
        self,
        *,
        verification_status: VerificationStatus | None = None,
        incident_type: IncidentType | None = None,
        minimum_confidence: int | None = None,
        country: str | None = None,
        source_kind: SourceKind | None = None,
    ) -> list[EarlyWarningIncident]:
        """Load all incidents from Chroma, then filter and sort in memory.

        Args:
            verification_status: Filter by verification status.
            incident_type: Filter by incident type.
            minimum_confidence: Minimum confidence score inclusive.
            country: Case-insensitive country filter.
            source_kind: Filter by source kind.

        Returns:
            Matching incidents, newest effective publication date first.
        """
        results = self.collection.get(include=["documents", "metadatas"])
        ids = results.get("ids") or []
        documents = results.get("documents") or []
        metadatas = results.get("metadatas") or []
        incidents: list[EarlyWarningIncident] = []
        for index, incident_id in enumerate(ids):
            document = documents[index] if index < len(documents) else None
            metadata = metadatas[index] if index < len(metadatas) else None
            incident = self._parse_record(incident_id, document, metadata)
            if incident is not None:
                incidents.append(incident)
        return _filter_and_sort(
            incidents,
            verification_status=verification_status,
            incident_type=incident_type,
            minimum_confidence=minimum_confidence,
            country=country,
            source_kind=source_kind,
        )

    def get_incident(self, incident_id: str) -> EarlyWarningIncident | None:
        """Fetch a single incident by ID from Chroma.

        Args:
            incident_id: Unique incident ID.

        Returns:
            Parsed incident, or None if missing/blank/unparsable.
        """
        key = incident_id.strip()
        if not key:
            return None
        results = self.collection.get(ids=[key], include=["documents", "metadatas"])
        ids = results.get("ids") or []
        if not ids:
            return None
        documents = results.get("documents") or []
        metadatas = results.get("metadatas") or []
        return self._parse_record(
            ids[0],
            documents[0] if documents else None,
            metadatas[0] if metadatas else None,
        )

    def upsert_incident(self, incident: EarlyWarningIncident) -> EarlyWarningIncident:
        """Insert or replace an incident document and metadata in Chroma.

        Args:
            incident: Incident to persist.

        Returns:
            The same incident after upsert.
        """
        self.collection.upsert(
            ids=[incident.incident_id],
            documents=[incident.to_document()],
            metadatas=[cast(Metadata, incident.to_metadata())],
        )
        return incident

    def delete_incident(self, incident_id: str) -> bool:
        """Delete an incident if it exists.

        Args:
            incident_id: Unique incident ID.

        Returns:
            True if deleted; False if not found.
        """
        existing = self.get_incident(incident_id)
        if existing is None:
            return False
        self.collection.delete(ids=[existing.incident_id])
        return True

    def count_incidents(self) -> int:
        """Return the number of incident documents in the collection.

        Returns:
            Total incident count.
        """
        results = self.collection.get(include=[])
        return len(results.get("ids") or [])

    def _parse_record(
        self,
        incident_id: str,
        document: str | None,
        metadata: Metadata | None,
    ) -> EarlyWarningIncident | None:
        """Parse an incident from document JSON, falling back to metadata.

        Args:
            incident_id: Chroma document ID used if metadata omits it.
            document: Raw document JSON string, if present.
            metadata: Chroma metadata dict, if present.

        Returns:
            Parsed incident, or None if both sources fail.
        """
        if document:
            try:
                return EarlyWarningIncident.from_document(document)
            except (ValueError, TypeError):
                pass
        if not metadata:
            return None
        try:
            payload = dict(metadata)
            payload.setdefault("incident_id", incident_id)
            return EarlyWarningIncident.from_metadata(payload)
        except (KeyError, TypeError, ValueError):
            return None

    # Convenient aliases for service/API callers.
    get_incidents = list_incidents
    save_incident = upsert_incident

class InMemoryEarlyWarningIncidentStore(EarlyWarningIncidentsDBInterface):
    """Deterministic test double with the same update semantics as Chroma upsert."""

    def __init__(self) -> None:
        """Initialize an empty in-memory incident map."""
        self._incidents: dict[str, EarlyWarningIncident] = {}

    def list_incidents(
        self,
        *,
        verification_status: VerificationStatus | None = None,
        incident_type: IncidentType | None = None,
        minimum_confidence: int | None = None,
        country: str | None = None,
        source_kind: SourceKind | None = None,
    ) -> list[EarlyWarningIncident]:
        """List deep-copied incidents after applying filters.

        Args:
            verification_status: Filter by verification status.
            incident_type: Filter by incident type.
            minimum_confidence: Minimum confidence score inclusive.
            country: Case-insensitive country filter.
            source_kind: Filter by source kind.

        Returns:
            Deep copies of matching incidents.
        """
        return [
            incident.model_copy(deep=True)
            for incident in _filter_and_sort(
                self._incidents.values(),
                verification_status=verification_status,
                incident_type=incident_type,
                minimum_confidence=minimum_confidence,
                country=country,
                source_kind=source_kind,
            )
        ]

    def get_incident(self, incident_id: str) -> EarlyWarningIncident | None:
        """Fetch a deep copy of an incident by ID.

        Args:
            incident_id: Unique incident ID.

        Returns:
            Deep-copied incident, or None if not found.
        """
        incident = self._incidents.get(incident_id.strip())
        return incident.model_copy(deep=True) if incident is not None else None

    def upsert_incident(self, incident: EarlyWarningIncident) -> EarlyWarningIncident:
        """Store a deep copy of the incident and return another copy.

        Args:
            incident: Incident to persist.

        Returns:
            Deep copy of the stored incident.
        """
        stored = incident.model_copy(deep=True)
        self._incidents[stored.incident_id] = stored
        return stored.model_copy(deep=True)

    def delete_incident(self, incident_id: str) -> bool:
        """Delete an incident from the in-memory map.

        Args:
            incident_id: Unique incident ID.

        Returns:
            True if deleted; False if not found.
        """
        key = incident_id.strip()
        if key not in self._incidents:
            return False
        del self._incidents[key]
        return True

    def count_incidents(self) -> int:
        """Return the number of incidents in memory.

        Returns:
            Total incident count.
        """
        return len(self._incidents)

    get_incidents = list_incidents
    save_incident = upsert_incident

# Legacy aliases for older import paths
InMemoryEarlyWarningStore = InMemoryEarlyWarningIncidentStore
EarlyWarningChromaClient = EarlyWarningIncidentsChromaClient

def _filter_and_sort(
    incidents: Iterable[EarlyWarningIncident],
    *,
    verification_status: VerificationStatus | None,
    incident_type: IncidentType | None,
    minimum_confidence: int | None,
    country: str | None,
    source_kind: SourceKind | None,
) -> list[EarlyWarningIncident]:
    """Apply optional filters and sort by publication date descending.

    Args:
        incidents: Incidents to filter.
        verification_status: Optional verification status filter.
        incident_type: Optional incident type filter.
        minimum_confidence: Optional minimum confidence inclusive.
        country: Optional case-insensitive country filter.
        source_kind: Optional source kind filter.

    Returns:
        Filtered list sorted by effective publication date, then ID.
    """
    selected = list(incidents)
    if verification_status is not None:
        selected = [
            incident
            for incident in selected
            if incident.verification_status == verification_status
        ]
    if incident_type is not None:
        selected = [
            incident for incident in selected if incident.incident_type == incident_type
        ]
    if minimum_confidence is not None:
        selected = [
            incident
            for incident in selected
            if incident.confidence_score >= minimum_confidence
        ]
    if country and country.strip():
        normalized_country = country.strip().casefold()
        selected = [
            incident
            for incident in selected
            if incident.country.casefold() == normalized_country
        ]
    if source_kind is not None:
        selected = [
            incident for incident in selected if incident.source_kind == source_kind
        ]
    return sorted(
        selected,
        key=lambda incident: (
            incident.effective_publication_date().isoformat(),
            incident.incident_id,
        ),
        reverse=True,
    )
