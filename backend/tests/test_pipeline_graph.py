import unittest
from datetime import date
from typing import Any
from unittest.mock import AsyncMock, patch

from agents.errors import SourceFetchError
from agents.graph import (
    repair_and_convert_node,
    run_pipeline,
    summarize_node,
    structure_node,
    translate_values_node,
)
from agents.llm import AgentOutputError
from agents.validators import AgentValidationError
from models.food_recall_alert import FoodRecallAlertCreate
from models.pipeline_options import PipelineRunOptions
from models.pipeline_state import PipelineRecordState
from models.source_record import SourceRecord
from models.pipeline_result import FetchSourcesResult

class PipelineGraphTests(unittest.IsolatedAsyncioTestCase):
    def test_repair_and_convert_restores_protected_values_from_original_json(self) -> None:
        source_record = _source_record()
        state: PipelineRecordState = {
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

        alert = result.get("alert")
        self.assertIsNotNone(alert)
        assert alert is not None
        self.assertIsInstance(alert, FoodRecallAlertCreate)
        self.assertEqual(alert.api_source, "uk")
        self.assertEqual(alert.product_name, "Original Product")
        self.assertEqual(alert.recall_date.isoformat(), "2026-06-09")
        self.assertEqual(alert.source_url, "https://source.example.com")
        self.assertEqual(
            alert.summary,
            "This product was recalled. It may be unsafe. Consumers should not eat it.",
        )

    def test_repair_and_convert_always_uses_record_api_source(self) -> None:
        source_record = _source_record(source="ca")
        state: PipelineRecordState = {
            "record": source_record,
            "summary": "Pipeline summary.",
            "structured_json": {
                "api_source": "malicious-override",
                "product_name": "Original Product",
                "product_category": "Produce",
                "recall_reason": "Possible contamination",
                "summary": "LLM summary",
                "recall_date": "2026-06-09",
                "risk_level": "High",
                "hazard_type": "Listeria",
                "consumer_action": "Do not consume it.",
                "source_url": "https://source.example.com",
                "affected_regions": [],
            },
        }

        result = repair_and_convert_node(state)

        structured_json = result.get("structured_json")
        alert = result.get("alert")
        self.assertIsNotNone(structured_json)
        self.assertIsNotNone(alert)
        assert structured_json is not None
        assert alert is not None
        self.assertEqual(structured_json["api_source"], "ca")
        self.assertEqual(alert.api_source, "ca")

    async def test_run_pipeline_with_mocked_fetch_and_agents(self) -> None:
        source_record = _source_record()
        options = _options(sources=["uk"], limit=1)

        with (
            patch(
                "agents.graph.fetch_sources_sequentially",
                new=AsyncMock(return_value=FetchSourcesResult(records=[source_record])),
            ),
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
            result = await run_pipeline(options)

        self.assertEqual(len(result.alerts), 1)
        self.assertIsInstance(result.alerts[0], FoodRecallAlertCreate)
        self.assertEqual(result.alerts[0].api_source, "uk")
        self.assertEqual(result.alerts[0].product_name, "Original Product")
        self.assertEqual(result.alerts[0].recall_date.isoformat(), "2026-06-09")
        self.assertEqual(result.alerts[0].source_url, "https://source.example.com")

    async def test_run_pipeline_uses_supplied_sources_and_limit(self) -> None:
        source_record = _source_record(source="ca")
        options = _options(sources=["ca", "uk"], limit=7)

        with (
            patch(
                "agents.graph.fetch_sources_sequentially",
                new=AsyncMock(return_value=FetchSourcesResult(records=[source_record])),
            ) as fetch_sources,
            patch("agents.graph.chat_json", side_effect=[source_record.working_json, _valid_structured_json()]),
            patch("agents.graph.chat_text", return_value=_valid_summary()),
        ):
            await run_pipeline(options)

        fetch_sources.assert_awaited_once_with(["ca", "uk"], limit=7)

    async def test_run_pipeline_allows_non_three_sentence_summary(self) -> None:
        source_record = _source_record()
        options = _options(sources=["uk"], limit=1)

        with (
            patch(
                "agents.graph.fetch_sources_sequentially",
                new=AsyncMock(return_value=FetchSourcesResult(records=[source_record])),
            ),
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
            result = await run_pipeline(options)

        self.assertEqual(len(result.alerts), 1)
        self.assertEqual(result.alerts[0].api_source, "uk")
        self.assertEqual(result.alerts[0].summary, "Short summary.")

    async def test_run_pipeline_skips_records_that_fail_processing(self) -> None:
        record_ok = _source_record(source="uk")
        record_bad = _source_record(source="ca")
        options = _options(sources=["uk", "ca"], limit=2)

        fake_graph = AsyncMock()
        fake_graph.ainvoke = AsyncMock(
            side_effect=[
                ValueError("invalid structured payload"),
                {"alert": _alert_for_source("ca")},
            ]
        )

        with (
            patch(
                "agents.graph.fetch_sources_sequentially",
                new=AsyncMock(return_value=FetchSourcesResult(records=[record_ok, record_bad])),
            ),
            patch("agents.graph.create_pipeline_graph", return_value=fake_graph),
        ):
            result = await run_pipeline(options)

        self.assertEqual(result.records_fetched, 2)
        self.assertEqual(len(result.alerts), 1)
        self.assertEqual(result.alerts[0].api_source, "ca")

    def test_structure_node_retries_invalid_agent3_schema(self) -> None:
        source_record = _source_record()
        state: PipelineRecordState = {
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
        structured_json = result.get("structured_json")
        self.assertIsNotNone(structured_json)
        assert structured_json is not None
        self.assertEqual(structured_json["product_category"], "Produce")

    async def test_run_pipeline_raises_when_all_sources_fail_to_fetch(self) -> None:
        options = _options(sources=["us"], limit=1)

        with patch(
            "agents.graph.fetch_sources_sequentially",
            new=AsyncMock(
                return_value=FetchSourcesResult(
                    records=[],
                    failures={"us": "Client error '403 Forbidden'"},
                )
            ),
        ):
            with self.assertRaises(SourceFetchError):
                await run_pipeline(options)

    def test_structure_node_falls_back_after_agent3_retry_failure(self) -> None:
        source_record = _source_record()
        state: PipelineRecordState = {
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

        structured_json = result.get("structured_json")
        self.assertIsNotNone(structured_json)
        assert structured_json is not None
        self.assertEqual(structured_json["api_source"], "uk")
        self.assertEqual(structured_json["product_name"], "Original Product")
        self.assertEqual(structured_json["recall_date"], "2026-06-09")
        self.assertEqual(structured_json["source_url"], "https://source.example.com")
        self.assertEqual(structured_json["summary"], "Short summary.")

    async def test_run_pipeline_keeps_source_failures_when_records_exist(self) -> None:
        source_record = _source_record(source="uk")
        options = _options(sources=["uk", "us"], limit=2)

        with (
            patch(
                "agents.graph.fetch_sources_sequentially",
                new=AsyncMock(
                    return_value=FetchSourcesResult(
                        records=[source_record],
                        failures={"us": "Timeout"},
                    )
                ),
            ),
            patch("agents.graph.chat_json", side_effect=[source_record.working_json, _valid_structured_json()]),
            patch("agents.graph.chat_text", return_value=_valid_summary()),
        ):
            result = await run_pipeline(options)

        self.assertEqual(result.records_fetched, 1)
        self.assertEqual(len(result.alerts), 1)
        self.assertEqual(result.source_failures, {"us": "Timeout"})

    async def test_run_pipeline_returns_empty_when_nothing_fetched_and_no_failures(self) -> None:
        options = _options(sources=["uk"], limit=1)

        with patch(
            "agents.graph.fetch_sources_sequentially",
            new=AsyncMock(return_value=FetchSourcesResult(records=[], failures={})),
        ):
            result = await run_pipeline(options)

        self.assertEqual(result.records_fetched, 0)
        self.assertEqual(result.alerts, [])
        self.assertEqual(result.source_failures, {})

    def test_translate_values_node_falls_back_to_original_on_validation_error(self) -> None:
        source_record = _source_record()
        state: PipelineRecordState = {"record": source_record}

        with patch(
            "agents.graph.chat_json",
            side_effect=AgentValidationError("invalid translation structure"),
        ):
            result = translate_values_node(state)

        translated_json = result.get("translated_json")
        self.assertIsNotNone(translated_json)
        self.assertEqual(translated_json, source_record.working_json)

    def test_translate_values_node_falls_back_to_original_on_agent_output_error(self) -> None:
        source_record = _source_record()
        state: PipelineRecordState = {"record": source_record}

        with patch("agents.graph.chat_json", side_effect=AgentOutputError("bad output")):
            result = translate_values_node(state)

        translated_json = result.get("translated_json")
        self.assertIsNotNone(translated_json)
        self.assertEqual(translated_json, source_record.working_json)

    def test_translate_values_node_uses_translated_payload_when_valid(self) -> None:
        source_record = _source_record()
        translated = {
            "source": "uk",
            "record": {
                "productDetails": [{"productName": "Nom du produit"}],
                "created": "2026-06-09",
                "alertURL": "https://source.example.com",
                "recall_reason": "Contamination possible",
                "consumer_action": "Ne pas consommer.",
            },
        }
        state: PipelineRecordState = {"record": source_record}

        with patch("agents.graph.chat_json", return_value=translated):
            result = translate_values_node(state)

        translated_json = result.get("translated_json")
        self.assertIsNotNone(translated_json)
        self.assertEqual(translated_json, translated)

    def test_summarize_node_returns_summary_for_valid_text(self) -> None:
        state: PipelineRecordState = {"translated_json": _source_record().working_json}

        with patch("agents.graph.chat_text", return_value="Valid summary text."):
            result = summarize_node(state)

        summary = result.get("summary")
        self.assertIsNotNone(summary)
        self.assertEqual(summary, "Valid summary text.")

    def test_summarize_node_raises_on_blank_summary(self) -> None:
        state: PipelineRecordState = {"translated_json": _source_record().working_json}

        with patch("agents.graph.chat_text", return_value="   "):
            with self.assertRaises(AgentValidationError):
                summarize_node(state)

    def test_structure_node_retry_prompt_includes_previous_error_reason(self) -> None:
        source_record = _source_record()
        state: PipelineRecordState = {
            "record": source_record,
            "translated_json": source_record.working_json,
            "summary": "Short summary.",
        }

        with patch(
            "agents.graph.chat_json",
            side_effect=[{"unexpected": "shape"}, _valid_structured_json()],
        ) as chat_json:
            structure_node(state)

        second_user_prompt = chat_json.call_args_list[1].kwargs["user_prompt"]
        self.assertIn("previous response could not be used", second_user_prompt)
        self.assertIn("missing required fields", second_user_prompt)

def _options(sources: list[str], limit: int) -> PipelineRunOptions:
    return PipelineRunOptions.model_construct(sources=sources, limit=limit)

def _valid_summary() -> str:
    return "This product was recalled. It may be unsafe. Consumers should not eat it."

def _valid_structured_json() -> dict[str, Any]:
    return {
        "product_name": "Original Product",
        "product_category": "Produce",
        "recall_reason": "Possible contamination",
        "summary": "LLM changed summary.",
        "recall_date": "1999-01-01",
        "risk_level": "High",
        "hazard_type": "Listeria",
        "consumer_action": "Do not consume it.",
        "source_url": "https://changed.example.com",
        "affected_regions": ["Ontario"],
    }

def _alert_for_source(source: str) -> FoodRecallAlertCreate:
    return FoodRecallAlertCreate(
        api_source=source,
        product_name="Original Product",
        product_category="Produce",
        recall_reason="Possible contamination",
        summary=_valid_summary(),
        recall_date=date(2026, 6, 9),
        risk_level="High",
        hazard_type="Listeria",
        consumer_action="Do not consume it.",
        source_url="https://source.example.com",
        affected_regions=[],
    )

def _source_record(source: str = "uk") -> SourceRecord:
    return SourceRecord(
        source=source,
        raw_record={
            "productDetails": [{"productName": "Original Product"}],
            "created": "2026-06-09",
            "alertURL": "https://source.example.com",
        },
        working_json={
            "source": source,
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
