import unittest
from datetime import date
from unittest.mock import AsyncMock, Mock, patch

from models.food_recall_alert import FoodRecallAlert, FoodRecallAlertCreate, api_source_to_country_source
from models.pipeline_options import PipelineRunOptions
from models.pipeline_result import AgentPipelineResult
from services.geocoding import Coordinates
from services.pipeline import PipelineService

class PipelineServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_pipeline_saves_each_alert_as_processed(self) -> None:
        first_alert = _alert_for_source("uk")
        second_alert = _alert_for_source("ca")
        first_saved = _saved_alert("saved-1", first_alert)
        db = Mock()
        db.save_alerts.side_effect = [[first_saved], []]
        db.update_alert_coordinates.return_value = True
        source_db = Mock()
        service = PipelineService(db, source_db)

        async def fake_run_agent_pipeline(options, *, source_db=None, reporter=None, on_alert_processed=None):
            assert source_db is service.source_db
            assert on_alert_processed is not None
            await on_alert_processed(first_alert)
            await on_alert_processed(second_alert)
            return AgentPipelineResult(
                alerts=[first_alert, second_alert],
                records_fetched=2,
                source_failures={},
            )

        with (
            patch("services.pipeline.run_agent_pipeline", side_effect=fake_run_agent_pipeline),
            patch(
                "services.pipeline.geocode_alert_location",
                new=AsyncMock(return_value=Coordinates(51.5, -0.1)),
            ) as geocode_mock,
        ):
            result = await service.run_pipeline(PipelineRunOptions.model_construct(sources=["uk", "ca"], limit=2))

        self.assertEqual(result.new_alerts_count, 1)
        self.assertEqual(result.records_fetched, 2)
        self.assertEqual(db.save_alerts.call_count, 2)
        db.save_alerts.assert_any_call([first_alert])
        db.save_alerts.assert_any_call([second_alert])
        geocode_mock.assert_awaited_once_with(first_alert)
        db.update_alert_coordinates.assert_called_once_with("saved-1", 51.5, -0.1)

    async def test_run_pipeline_notifies_broadcaster_after_each_insert(self) -> None:
        alerts = [
            _alert_for_source("uk"),
            _alert_for_source("ca"),
            _alert_for_source("us"),
        ]
        saved_alerts = [
            _saved_alert("saved-1", alerts[0]),
            _saved_alert("saved-3", alerts[2]),
        ]
        db = Mock()
        db.save_alerts.side_effect = [[saved_alerts[0]], [], [saved_alerts[1]]]
        db.update_alert_coordinates.return_value = True
        source_db = Mock()
        broadcaster = Mock()
        service = PipelineService(db, source_db, alert_broadcaster=broadcaster)

        async def fake_run_agent_pipeline(options, *, source_db=None, reporter=None, on_alert_processed=None):
            assert source_db is service.source_db
            assert on_alert_processed is not None
            for alert in alerts:
                await on_alert_processed(alert)
            return AgentPipelineResult(
                alerts=alerts,
                records_fetched=3,
                source_failures={},
            )

        with (
            patch("services.pipeline.run_agent_pipeline", side_effect=fake_run_agent_pipeline),
            patch(
                "services.pipeline.geocode_alert_location",
                new=AsyncMock(return_value=Coordinates(48.8, 2.3)),
            ),
        ):
            result = await service.run_pipeline(
                PipelineRunOptions.model_construct(sources=["uk", "ca", "us"], limit=3)
            )

        self.assertEqual(result.new_alerts_count, 2)
        self.assertEqual(broadcaster.notify.call_count, 2)
        broadcaster.notify.assert_any_call(1)
        self.assertEqual(db.update_alert_coordinates.call_count, 2)

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

def _saved_alert(alert_id: str, alert: FoodRecallAlertCreate) -> FoodRecallAlert:
    return FoodRecallAlert(alert_id=alert_id, **alert.model_dump())

if __name__ == "__main__":
    unittest.main()
