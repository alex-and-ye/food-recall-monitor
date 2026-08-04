"""Abstract persistence contract for early-warning incidents.

Defines the repository interface for listing, fetching, upserting, and
deleting early-warning incident records used by the monitoring pipeline.
"""

from abc import ABC, abstractmethod

from models.early_warning_incident import (
    EarlyWarningIncident,
    IncidentType,
    SourceKind,
    VerificationStatus,
)

class EarlyWarningIncidentsDBInterface(ABC):
    """Repository interface for early-warning incident persistence."""

    @abstractmethod
    def list_incidents(
        self,
        *,
        verification_status: VerificationStatus | None = None,
        incident_type: IncidentType | None = None,
        minimum_confidence: int | None = None,
        country: str | None = None,
        source_kind: SourceKind | None = None,
    ) -> list[EarlyWarningIncident]:
        """List incidents with optional filters.

        Args:
            verification_status: Filter by verification status.
            incident_type: Filter by incident type.
            minimum_confidence: Minimum confidence score inclusive.
            country: Filter by country (case-insensitive match expected).
            source_kind: Filter by source kind.

        Returns:
            Matching incidents, typically newest publication date first.
        """
        pass

    @abstractmethod
    def get_incident(self, incident_id: str) -> EarlyWarningIncident | None:
        """Fetch a single incident by identifier.

        Args:
            incident_id: Unique incident ID.

        Returns:
            The matching incident, or None if not found.
        """
        pass

    @abstractmethod
    def upsert_incident(self, incident: EarlyWarningIncident) -> EarlyWarningIncident:
        """Insert or replace an early-warning incident.

        Args:
            incident: Incident payload to store.

        Returns:
            The stored incident.
        """
        pass

    @abstractmethod
    def delete_incident(self, incident_id: str) -> bool:
        """Delete an incident by identifier.

        Args:
            incident_id: Unique incident ID.

        Returns:
            True if a record was deleted; False if not found.
        """
        pass

    @abstractmethod
    def count_incidents(self) -> int:
        """Return the total number of stored incidents.

        Returns:
            Count of incidents in the store.
        """
        pass

# Singular alias retained for callers that treat the repository as one aggregate.
EarlyWarningIncidentDBInterface = EarlyWarningIncidentsDBInterface
