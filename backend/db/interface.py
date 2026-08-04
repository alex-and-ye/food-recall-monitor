"""Abstract persistence contract for food recall alerts.

Defines the repository interface that concrete stores (e.g. ChromaDB)
must implement for reading, searching, saving, and versioning alerts.
"""

from abc import ABC, abstractmethod
from datetime import date
from typing import List, Optional

from models.food_recall_alert import FoodRecallAlert, FoodRecallAlertCreate, FoodRecallAlertsVersion

class FoodRecallAlertsDBInterface(ABC):
    """Repository interface for food recall alert persistence."""

    @abstractmethod
    def get_alerts(self) -> List[FoodRecallAlert]:
        """Return all stored food recall alerts.

        Returns:
            All alerts in the store, typically newest-first.
        """
        pass

    @abstractmethod
    def get_alert_by_id(self, alert_id: str) -> Optional[FoodRecallAlert]:
        """Fetch a single alert by its identifier.

        Args:
            alert_id: Unique alert ID.

        Returns:
            The matching alert, or None if not found.
        """
        pass

    @abstractmethod
    def search_alerts(
        self,
        search: str | None = None,
        risk_level: str | None = None,
        country_source: str | None = None,
        recall_date: date | None = None,
        sort_by: str | None = None,
    ) -> List[FoodRecallAlert]:
        """Search and filter alerts by optional criteria.

        Args:
            search: Free-text query matched against alert fields.
            risk_level: Filter by risk level value.
            country_source: Filter by country/source code.
            recall_date: Filter by exact recall date.
            sort_by: Sort order key (e.g. latest or oldest).

        Returns:
            Alerts matching the applied filters and sort.
        """
        pass

    @abstractmethod
    def save_alerts(self, alerts: List[FoodRecallAlertCreate]) -> List[FoodRecallAlert]:
        """Persist new or updated alerts with store-specific deduplication.

        Args:
            alerts: Alert payloads to insert or update.

        Returns:
            Alerts that were newly inserted or had content updates.
        """
        pass

    @abstractmethod
    def update_alert_coordinates(self, alert_id: str, latitude: float, longitude: float) -> bool:
        """Update geolocation coordinates for an existing alert.

        Args:
            alert_id: Unique alert ID.
            latitude: Latitude in decimal degrees.
            longitude: Longitude in decimal degrees.

        Returns:
            True if the alert was found and updated; False otherwise.
        """
        pass

    @abstractmethod
    def get_alerts_version(self) -> FoodRecallAlertsVersion:
        """Return a version fingerprint for change detection.

        Returns:
            Count and fingerprint summarizing the current alert set.
        """
        pass
