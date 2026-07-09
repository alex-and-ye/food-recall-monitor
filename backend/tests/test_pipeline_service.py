import unittest
from datetime import date
from unittest.mock import Mock, patch

from models.food_recall_alert import FoodRecallAlertCreate, api_source_to_country_source
from models.pipeline_options import PipelineRunOptions
from models.pipeline_result import AgentPipelineResult
from services.pipeline import PipelineService

class PipelineServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_pipeline_saves_each_alert_as_processed(self) -> None:
        db = Mock()
        db.save_alerts.side_effect = [1, 0]
        service = PipelineService(db)
        first_alert = _alert_for_source("uk")
        second_alert = _alert_for_source("ca")

        async def fake_run_agent_pipeline(options, *, reporter=None, on_alert_processed=None):
            assert on_alert_processed is not None
            on_alert_processed(first_alert)
            on_alert_processed(second_alert)
            return AgentPipelineResult(
                alerts=[first_alert, second_alert],
                records_fetched=2,
                source_failures={},
            )

        with patch("services.pipeline.run_agent_pipeline", side_effect=fake_run_agent_pipeline):
            result = await service.run_pipeline(PipelineRunOptions.model_construct(sources=["uk", "ca"], limit=2))

        self.assertEqual(result.new_alerts_count, 1)
        self.assertEqual(result.records_fetched, 2)
        self.assertEqual(db.save_alerts.call_count, 2)
        db.save_alerts.assert_any_call([first_alert])
        db.save_alerts.assert_any_call([second_alert])

    async def test_run_pipeline_notifies_broadcaster_with_total_saved_count(self) -> None:
        db = Mock()
        db.save_alerts.side_effect = [1, 1]
        broadcaster = Mock()
        service = PipelineService(db, alert_broadcaster=broadcaster)
        alerts = [_alert_for_source("uk"), _alert_for_source("ca")]

        async def fake_run_agent_pipeline(options, *, reporter=None, on_alert_processed=None):
            assert on_alert_processed is not None
            for alert in alerts:
                on_alert_processed(alert)
            return AgentPipelineResult(
                alerts=alerts,
                records_fetched=2,
                source_failures={},
            )

        with patch("services.pipeline.run_agent_pipeline", side_effect=fake_run_agent_pipeline):
            await service.run_pipeline(PipelineRunOptions.model_construct(sources=["uk", "ca"], limit=2))

        broadcaster.notify.assert_called_once_with(2)

def _alert_for_source(source: str) -> FoodRecallAlertCreate:
    return FoodRecallAlertCreate(
        api_source=source,
        country_source=api_source_to_country_source(source),
        product_name="Original Product",
        product_category="Produce",
        recall_reason="Possible contamination",
        summary="This product was recalled. It may be unsafe. Consumers should not eat it.",
        recall_date=date(2026, 6, 9),
        risk_level="High",
        hazard_type="Listeria",
        consumer_action="Do not consume it.",
        source_url="https://source.example.com/recalls/abc",
        affected_regions=[],
    )

if __name__ == "__main__":
    unittest.main()
