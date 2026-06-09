from datetime import date

from db.interface import FoodRecallAlertsDBInterface
from models.food_recall_alert import FoodRecallAlert

class PipelineService:
    def __init__(self, db: FoodRecallAlertsDBInterface) -> None:
        self.db = db

    async def run_pipeline(self) -> int:
        # TODO: Trigger AI Agents Pipeline here

        # mock data for testing
        extracted_alerts = [
            FoodRecallAlert(
                alert_id="TEST-2026-001",
                product_name="Sample Spinach",
                product_category="Produce",
                recall_reason="Potential E. coli contamination",
                summary="A batch of bagged spinach was recalled during testing.",
                recall_date=date.today(),
                risk_level="High",
                hazard_type="Biological",
                consumer_action="Discard immediately.",
                source_url="https://example.com/recall-notice",
                affected_regions=["Ontario", "Quebec"]
            )
        ]

        if not extracted_alerts:
            return 0
        
        return self.db.save_alerts(extracted_alerts)