import unittest
from datetime import date
from unittest.mock import AsyncMock, patch

from agents.graph import repair_and_convert_node, run_pipeline
from agents.source_types import ProtectedFields, SourceRecord
from models.food_recall_alert import FoodRecallAlertCreate
from models.pipeline_options import PipelineRunOptions, RecallSource


class PipelineGraphTests(unittest.IsolatedAsyncioTestCase):
    def test_repair_and_convert_overwrites_protected_fields(self) -> None:
        source_record = _source_record()
        state = {
            "record": source_record,
            "summary": "This product was recalled. It may be unsafe. Consumers should not eat it.",
            "structured_json": {
                "product_name": "LLM changed name",
                "product_category": "Produce",
                "recall_reason": "Possible contamination",
                "summary": "LLM changed summary.",
                "recall_date": "1999-01-01",
                "risk_level": "High",
                "hazard_type": "Listeria",
                "consumer_action": "Do not consume it.",
                "source_url": "https://changed.example.com",
                "affected_regions": ["Ontario"],
            },
        }

        result = repair_and_convert_node(state)

        alert = result["alert"]
        self.assertIsInstance(alert, FoodRecallAlertCreate)
        self.assertEqual(alert.product_name, "Original Product")
        self.assertEqual(alert.recall_date.isoformat(), "2026-06-09")
        self.assertEqual(alert.source_url, "https://source.example.com")
        self.assertEqual(
            alert.summary,
            "This product was recalled. It may be unsafe. Consumers should not eat it.",
        )

    async def test_run_pipeline_with_mocked_fetch_and_agents(self) -> None:
        source_record = _source_record()
        options = PipelineRunOptions(sources=[RecallSource.UK], limit=1)

        with (
            patch("agents.graph.fetch_sources_sequentially", new=AsyncMock(return_value=[source_record])),
            patch(
                "agents.graph.chat_json",
                side_effect=[
                    source_record.working_json,
                    {
                        "product_name": "LLM changed name",
                        "product_category": "Produce",
                        "recall_reason": "Possible contamination",
                        "summary": "LLM changed summary.",
                        "recall_date": "1999-01-01",
                        "risk_level": "High",
                        "hazard_type": "Listeria",
                        "consumer_action": "Do not consume it.",
                        "source_url": "https://changed.example.com",
                        "affected_regions": ["Ontario"],
                    },
                ],
            ),
            patch(
                "agents.graph.chat_text",
                return_value="This product was recalled. It may be unsafe. Consumers should not eat it.",
            ),
        ):
            alerts = await run_pipeline(options)

        self.assertEqual(len(alerts), 1)
        self.assertIsInstance(alerts[0], FoodRecallAlertCreate)
        self.assertEqual(alerts[0].product_name, "Original Product")
        self.assertEqual(alerts[0].recall_date.isoformat(), "2026-06-09")
        self.assertEqual(alerts[0].source_url, "https://source.example.com")


def _source_record() -> SourceRecord:
    return SourceRecord(
        source=RecallSource.UK,
        raw_record={"id": "raw"},
        protected_fields=ProtectedFields(
            product_name="Original Product",
            recall_date=date(2026, 6, 9),
            source_url="https://source.example.com",
        ),
        working_json={
            "source": "uk",
            "recall_reason": "Possible contamination",
            "consumer_action": "Do not consume it.",
        },
    )


if __name__ == "__main__":
    unittest.main()
