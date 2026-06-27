from collections import Counter
from datetime import date, timedelta
from typing import List

from db.interface import FoodRecallAlertsDBInterface
from models.food_recall_alert import FoodRecallAlert, FoodRecallAlertStats

class AlertsService:
    def __init__(self, db: FoodRecallAlertsDBInterface) -> None:
        self.db = db

    def get_alerts(self) -> List[FoodRecallAlert]:
        return self.db.get_alerts()

    def get_alert_stats(self) -> FoodRecallAlertStats:
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