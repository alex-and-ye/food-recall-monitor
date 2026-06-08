from typing import List, Dict, Any

from db.interface import FoodRecallAlertsDBInterface
from models.recall_alert import FoodRecallAlert

class AlertsService:
    def __init__(self, db: FoodRecallAlertsDBInterface):
        self.db = db

    def get_alerts(self) -> List[FoodRecallAlert]:
        return self.db.get_alerts()
    
    def get_alert_stats(self) -> Dict[str, Any]:
        alerts = self.db.get_alerts()

        if not alerts:
            return {
                "total_alerts": 0,
                "top_hazard_type": "None",
                "active_regions": 0
            }
        
        total_alerts = len(alerts)
        
        hazard_type_counts = {}

        active_regions = set()

        for alert in alerts:
            hazard_type_counts[alert.hazard_type] = hazard_type_counts.get(alert.hazard_type, 0) + 1
            
            for region in alert.affected_regions:
                active_regions.add(region)

        top_hazard_type = max(hazard_type_counts, key=lambda k: hazard_type_counts[k])

        return {
            "total_alerts": total_alerts,
            "top_hazard_type": top_hazard_type,
            "active_regions": len(active_regions)
        }