import unittest
from unittest.mock import AsyncMock, patch

from agents.graph import repair_and_convert_node, run_pipeline, structure_node
from agents.source_types import SourceRecord
from models.food_recall_alert import FoodRecallAlertCreate
from models.pipeline_options import PipelineRunOptions


class PipelineGraphTests(unittest.IsolatedAsyncioTestCase):
    def test_repair_and_convert_restores_protected_values_from_original_json(self) -> None:
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
        options = PipelineRunOptions(sources=["uk"], limit=1)

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

    async def test_run_pipeline_allows_non_three_sentence_summary(self) -> None:
        source_record = _source_record()
        options = PipelineRunOptions(sources=["uk"], limit=1)

        with (
            patch("agents.graph.fetch_sources_sequentially", new=AsyncMock(return_value=[source_record])),
            patch(
                "agents.graph.chat_json",
                side_effect=[
                    source_record.working_json,
                    {
                        "product_name": "Original Product",
                        "product_category": "Produce",
                        "recall_reason": "Possible contamination",
                        "summary": "Short summary.",
                        "recall_date": "2026-06-09",
                        "risk_level": "High",
                        "hazard_type": "Listeria",
                        "consumer_action": "Do not consume it.",
                        "source_url": "https://source.example.com",
                        "affected_regions": [],
                    },
                ],
            ),
            patch("agents.graph.chat_text", return_value="Short summary."),
        ):
            alerts = await run_pipeline(options)

        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].summary, "Short summary.")

    def test_structure_node_retries_invalid_agent3_schema(self) -> None:
        source_record = _source_record()
        state = {
            "record": source_record,
            "translated_json": source_record.working_json,
            "summary": "Short summary.",
        }

        with patch(
            "agents.graph.chat_json",
            side_effect=[
                {"unexpected": "shape"},
                {
                    "product_name": "Original Product",
                    "product_category": "Produce",
                    "recall_reason": "Possible contamination",
                    "summary": "Short summary.",
                    "recall_date": "2026-06-09",
                    "risk_level": "High",
                    "hazard_type": "Listeria",
                    "consumer_action": "Do not consume it.",
                    "source_url": "https://source.example.com",
                    "affected_regions": [],
                },
            ],
        ) as chat_json:
            result = structure_node(state)

        self.assertEqual(chat_json.call_count, 2)
        self.assertEqual(result["structured_json"]["product_category"], "Produce")

    def test_structure_node_falls_back_after_agent3_retry_failure(self) -> None:
        source_record = _source_record()
        state = {
            "record": source_record,
            "translated_json": source_record.working_json,
            "summary": "Short summary.",
        }

        with patch(
            "agents.graph.chat_json",
            side_effect=[
                {"unexpected": "shape"},
                {"still": "wrong"},
            ],
        ):
            result = structure_node(state)

        structured_json = result["structured_json"]
        self.assertEqual(structured_json["product_name"], "Original Product")
        self.assertEqual(structured_json["recall_date"], "2026-06-09")
        self.assertEqual(structured_json["source_url"], "https://source.example.com")
        self.assertEqual(structured_json["summary"], "Short summary.")


def _source_record() -> SourceRecord:
    return SourceRecord(
        source="uk",
        raw_record={
            "productDetails": [{"productName": "Original Product"}],
            "created": "2026-06-09",
            "alertURL": "https://source.example.com",
        },
        working_json={
            "source": "uk",
            "record": {
                "productDetails": [{"productName": "Original Product"}],
                "created": "2026-06-09",
                "alertURL": "https://source.example.com",
                "recall_reason": "Possible contamination",
                "consumer_action": "Do not consume it.",
            },
        },
    )


if __name__ == "__main__":
    unittest.main()
