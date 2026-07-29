from __future__ import annotations

from abc import ABC, abstractmethod

from models.early_warning_incident import (
    EarlyWarningIncident,
    IncidentType,
    SourceKind,
    VerificationStatus,
)


class EarlyWarningIncidentsDBInterface(ABC):
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
        pass

    @abstractmethod
    def get_incident(self, incident_id: str) -> EarlyWarningIncident | None:
        pass

    @abstractmethod
    def upsert_incident(self, incident: EarlyWarningIncident) -> EarlyWarningIncident:
        pass

    @abstractmethod
    def delete_incident(self, incident_id: str) -> bool:
        pass

    @abstractmethod
    def count_incidents(self) -> int:
        pass


# Singular alias retained for callers that treat the repository as one aggregate.
EarlyWarningIncidentDBInterface = EarlyWarningIncidentsDBInterface
