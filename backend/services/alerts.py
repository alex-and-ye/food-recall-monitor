"""Service layer for querying and aggregating food-recall alerts.

Provides a thin facade over the alerts database interface with derived
statistics such as top hazards, product categories, and recent counts.
"""

from collections import Counter
from datetime import date, timedelta
from typing import List, Optional

from db.interface import FoodRecallAlertsDBInterface
from models.food_recall_alert import FoodRecallAlert, FoodRecallAlertStats, FoodRecallAlertsVersion


class AlertsService:
    """Read and aggregate persisted food-recall alerts."""

    def __init__(self, db: FoodRecallAlertsDBInterface) -> None:
        """Initialize the service with an alerts database backend.

        Args:
            db: Database interface used for alert reads.
        """
        self.db = db

    def get_alerts(self) -> List[FoodRecallAlert]:
        """Return all stored food-recall alerts.

        Returns:
            List of all alerts from the database.
        """
        return self.db.get_alerts()

    def get_alerts_version(self) -> FoodRecallAlertsVersion:
        """Return a version fingerprint for the current alert set.

        Returns:
            Version metadata describing the current alerts collection.
        """
        return self.db.get_alerts_version()

    def get_alert_by_id(self, alert_id: str) -> Optional[FoodRecallAlert]:
        """Fetch a single alert by its identifier.

        Args:
            alert_id: Unique alert identifier.

        Returns:
            The matching alert, or None if not found.
        """
        return self.db.get_alert_by_id(alert_id)

    def search_alerts(
        self,
        search: str | None = None,
        risk_level: str | None = None,
        country_source: str | None = None,
        recall_date: date | None = None,
        sort_by: str | None = None,
    ) -> List[FoodRecallAlert]:
        """Search and filter alerts by the given optional criteria.

        Args:
            search: Free-text search query.
            risk_level: Optional risk-level filter.
            country_source: Optional country/source filter.
            recall_date: Optional exact recall-date filter.
            sort_by: Optional sort key.

        Returns:
            Filtered list of matching alerts.
        """
        return self.db.search_alerts(
            search=search,
            risk_level=risk_level,
            country_source=country_source,
            recall_date=recall_date,
            sort_by=sort_by,
        )

    def get_alert_stats(self) -> FoodRecallAlertStats:
        """Compute aggregate statistics over all stored alerts.

        Returns:
            Summary stats including totals, top-5 breakdowns, and recent counts.
        """
        alerts = self.db.get_alerts()

        if not alerts:
            return FoodRecallAlertStats(
                total_alerts=0,
                top_5_hazard_types=[],
                top_5_product_categories=[],
                top_5_affected_regions=[],
                alerts_last_7_days=0,
                alerts_last_30_days=0,
            )

        today = date.today()
        seven_days_ago = today - timedelta(days=7)
        thirty_days_ago = today - timedelta(days=30)

        hazard_types: Counter[str] = Counter()
        product_categories: Counter[str] = Counter()
        affected_regions: Counter[str] = Counter()
        alerts_last_7_days = 0
        alerts_last_30_days = 0

        for alert in alerts:
            hazard_types[alert.hazard_type] += 1
            product_categories[alert.product_category] += 1
            affected_regions.update(alert.affected_regions)
            if alert.recall_date >= seven_days_ago:
                alerts_last_7_days += 1
            if alert.recall_date >= thirty_days_ago:
                alerts_last_30_days += 1

        hazard_type_counts = dict(hazard_types)
        product_category_counts = dict(product_categories)
        affected_region_counts = dict(affected_regions)

        return FoodRecallAlertStats(
            total_alerts=len(alerts),
            top_5_hazard_types=Counter(hazard_type_counts).most_common(5),
            top_5_product_categories=Counter(product_category_counts).most_common(5),
            top_5_affected_regions=Counter(affected_region_counts).most_common(5),
            alerts_last_7_days=alerts_last_7_days,
            alerts_last_30_days=alerts_last_30_days,
        )
