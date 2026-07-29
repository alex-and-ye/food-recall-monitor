from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from db.early_warning_interface import EarlyWarningIncidentsDBInterface
from models.early_warning_incident import EarlyWarningIncident, VerificationStatus
from models.food_recall_alert import FoodRecallAlert
from services.early_warning.matching import MatchResult, find_official_match


class OfficialRecallReader(Protocol):
    def get_alerts(self) -> list[FoodRecallAlert]: ...


@dataclass(frozen=True)
class VerificationResult:
    incident: EarlyWarningIncident
    official_alert: FoodRecallAlert | None
    match: MatchResult | None

    @property
    def confirmed(self) -> bool:
        return self.official_alert is not None


class IncidentVerificationService:
    """Links official recalls by updating incidents only."""

    def __init__(
        self,
        incident_store: EarlyWarningIncidentsDBInterface,
        official_store: OfficialRecallReader | None = None,
        *,
        date_window_days: int = 7,
    ) -> None:
        self.incident_store = incident_store
        self.official_store = official_store
        self.date_window_days = date_window_days

    def verify_incident(
        self,
        incident_id: str,
        official_alerts: Iterable[FoodRecallAlert] | None = None,
    ) -> VerificationResult | None:
        incident = self.incident_store.get_incident(incident_id)
        if incident is None:
            return None
        alerts = list(official_alerts) if official_alerts is not None else self._official_alerts()
        official_match = find_official_match(
            incident,
            alerts,
            date_window_days=self.date_window_days,
        )
        if official_match is None:
            return VerificationResult(incident=incident, official_alert=None, match=None)

        alert, match = official_match
        updated = link_official_recall(incident, alert.alert_id, match=match)
        if updated != incident:
            updated = self.incident_store.upsert_incident(updated)
        return VerificationResult(incident=updated, official_alert=alert, match=match)

    def verify_unresolved(
        self,
        official_alerts: Iterable[FoodRecallAlert] | None = None,
    ) -> list[VerificationResult]:
        alerts = list(official_alerts) if official_alerts is not None else self._official_alerts()
        results: list[VerificationResult] = []
        for incident in self.incident_store.list_incidents():
            if incident.verification_status in {
                VerificationStatus.DISMISSED,
                VerificationStatus.SUPERSEDED,
                VerificationStatus.OFFICIALLY_CONFIRMED,
            }:
                continue
            result = self.verify_incident(incident.incident_id, alerts)
            if result is not None:
                results.append(result)
        return results

    def _official_alerts(self) -> list[FoodRecallAlert]:
        if self.official_store is None:
            return []
        return self.official_store.get_alerts()


VerificationService = IncidentVerificationService


def link_official_recall(
    incident: EarlyWarningIncident,
    official_alert_id: str,
    *,
    match: MatchResult | None = None,
    at: datetime | None = None,
) -> EarlyWarningIncident:
    alert_id = official_alert_id.strip()
    if not alert_id:
        raise ValueError("official_alert_id must be non-empty")
    linked_ids = list(dict.fromkeys([*incident.linked_official_alert_ids, alert_id]))
    if (
        incident.verification_status == VerificationStatus.OFFICIALLY_CONFIRMED
        and linked_ids == incident.linked_official_alert_ids
        and incident.confidence_score == 100
    ):
        return incident

    reason = f"official recall {alert_id} linked"
    if match is not None:
        reason += f" by {match.kind.value}"
    return incident.model_copy(
        update={
            "verification_status": VerificationStatus.OFFICIALLY_CONFIRMED,
            "confidence_score": 100,
            "confidence_reasons": [f"{reason}: score set to 100"],
            "linked_official_alert_ids": linked_ids,
            "status_updated_at": at or datetime.now(timezone.utc),
        }
    )
