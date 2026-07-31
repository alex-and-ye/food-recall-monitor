import unittest
from datetime import date
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

from agents.errors import SourceFetchError
from agents.graph import (
    repair_and_convert_node,
    run_pipeline,
    summarize_node,
    structure_node,
    translate_values_node,
)
from agents.validators import AgentValidationError
from models.food_recall_alert import FoodRecallAlertCreate, web_source_to_country_source
from models.pipeline_options import PipelineRunOptions
from models.pipeline_result import FetchSourcesResult
from models.pipeline_state import PipelineRecordState
from models.scraped_record import ScrapedRecallRecord

class PipelineGraphTests(unittest.IsolatedAsyncioTestCase):
    def test_repair_and_convert_restores_deterministic_values_from_payload(self) -> None:
        scraped_record = _scraped_record()
        state: PipelineRecordState = {
            "record": scraped_record,
            "summary": _valid_summary(),
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
                "batch_id": "LOT-ABC-123",
                "country_source": "UK",
                "affected_regions": ["Ontario"],
            },
        }

        result = repair_and_convert_node(state)
        alert = result["alert"]
        self.assertEqual(alert.web_source, "uk")
        self.assertEqual(alert.product_name, "LLM changed name")
        self.assertEqual(alert.recall_date.isoformat(), "2026-06-09")
        self.assertEqual(alert.source_url, "https://source.example.com/recalls/abc")
        self.assertEqual(alert.summary, _valid_summary())

    def test_repair_and_convert_keeps_llm_product_name_over_page_heading(self) -> None:
        scraped_record = ScrapedRecallRecord(
            source_name="france",
            payload={
                "source_url": "https://rappel.conso.gouv.fr/fiche-rappel/22622/Interne",
                "headings": ["Flux RSS - veille, abonnement", "Produit"],
                "visible_text": "ORIENTAL KITCHEN NEM CHUA et NEM CHUA La Tam Ruot rappelés.",
                "selected_recall_date": "2026-06-25",
            },
        )
        state: PipelineRecordState = {
            "record": scraped_record,
            "summary": _valid_summary(),
            "structured_json": {
                "product_name": "NEM CHUA and NEM CHUA La Tam Ruot",
                "product_category": "Meat",
                "recall_reason": "Possible contamination",
                "summary": "LLM summary",
                "recall_date": "2026-06-25",
                "risk_level": "High",
                "hazard_type": "Listeria monocytogenes",
                "consumer_action": "Do not consume it.",
                "source_url": "https://changed.example.com",
                "batch_id": "LOT-NEM-2026",
                "country_source": "France",
                "affected_regions": [],
            },
        }

        result = repair_and_convert_node(state)

        self.assertEqual(result["alert"].product_name, "NEM CHUA and NEM CHUA La Tam Ruot")
        self.assertEqual(result["structured_json"]["source_url"], "https://rappel.conso.gouv.fr/fiche-rappel/22622/Interne")

    def test_repair_and_convert_always_uses_source_context_for_web_source(self) -> None:
        scraped_record = _scraped_record(source_name="ca")
        state: PipelineRecordState = {
            "record": scraped_record,
            "summary": "Pipeline summary.",
            "structured_json": {
                "web_source": "malicious-override",
                "product_name": "Original Product",
                "product_category": "Produce",
                "recall_reason": "Possible contamination",
                "summary": "LLM summary",
                "recall_date": "2026-06-09",
                "risk_level": "High",
                "hazard_type": "Listeria",
                "consumer_action": "Do not consume it.",
                "source_url": "https://source.example.com/recalls/abc",
                "batch_id": "",
                "country_source": "Canada",
                "affected_regions": [],
            },
        }

        result = repair_and_convert_node(state)
        self.assertEqual(result["structured_json"]["web_source"], "ca")
        self.assertEqual(result["alert"].web_source, "ca")
        self.assertEqual(result["alert"].country_source, "Canada")

    def test_repair_and_convert_uses_agent_country_source(self) -> None:
        scraped_record = _scraped_record(source_name="uk")
        state: PipelineRecordState = {
            "record": scraped_record,
            "summary": _valid_summary(),
            "structured_json": {
                "product_name": "Original Product",
                "product_category": "Produce",
                "recall_reason": "Possible contamination",
                "summary": "LLM summary",
                "recall_date": "2026-06-09",
                "risk_level": "High",
                "hazard_type": "Listeria",
                "consumer_action": "Do not consume it.",
                "source_url": "https://source.example.com/recalls/abc",
                "batch_id": "",
                "country_source": "United Kingdom",
                "affected_regions": [],
            },
        }

        result = repair_and_convert_node(state)
        self.assertEqual(result["alert"].web_source, "uk")
        self.assertEqual(result["alert"].country_source, "United Kingdom")

    def test_repair_and_convert_keeps_valid_llm_recall_date_when_scraper_date_is_generic(self) -> None:
        scraped_record = _scraped_record()
        scraped_record.payload["selected_recall_date"] = "2026-06-24"
        scraped_record.payload["selected_recall_date_source"] = "generic"
        state: PipelineRecordState = {
            "record": scraped_record,
            "summary": _valid_summary(),
            "structured_json": {
                "product_name": "Original Product",
                "product_category": "Produce",
                "recall_reason": "Possible contamination",
                "summary": "LLM summary",
                "recall_date": "2026-06-04",
                "risk_level": "High",
                "hazard_type": "Listeria",
                "consumer_action": "Do not consume it.",
                "source_url": "https://changed.example.com",
                "batch_id": "LOT-ABC-123",
                "country_source": "UK",
                "affected_regions": [],
            },
        }

        result = repair_and_convert_node(state)

        self.assertEqual(result["structured_json"]["recall_date"], "2026-06-04")
        self.assertEqual(result["alert"].recall_date.isoformat(), "2026-06-04")

    async def test_run_pipeline_with_mocked_fetch_and_agents(self) -> None:
        scraped_record = _scraped_record()
        options = _options(sources=["uk"], limit=1)

        with (
            patch(
                "agents.graph.fetch_sources_sequentially",
                new=AsyncMock(return_value=FetchSourcesResult(records=[scraped_record])),
            ),
            patch(
                "agents.graph.chat_json",
                side_effect=[
                    {"record": scraped_record.payload},
                    _valid_structured_json(),
                ],
            ),
            patch("agents.graph.chat_text", return_value=_valid_summary()),
        ):
            result = await run_pipeline(options, source_db=_source_db())

        self.assertEqual(len(result.alerts), 1)
        self.assertEqual(result.alerts[0].web_source, "uk")
        self.assertEqual(result.alerts[0].country_source, "UK")
        self.assertEqual(result.alerts[0].source_url, "https://source.example.com/recalls/abc")

    async def test_run_pipeline_uses_supplied_sources_and_limit(self) -> None:
        options = _options(sources=["ca", "uk"], limit=7)
        source_db = _source_db()

        with (
            patch(
                "agents.graph.fetch_sources_sequentially",
                new=AsyncMock(return_value=FetchSourcesResult(records=[_scraped_record("ca")])),
            ) as fetch_sources,
            patch("agents.graph.chat_json", side_effect=[{"record": _scraped_record().payload}, _valid_structured_json()]),
            patch("agents.graph.chat_text", return_value=_valid_summary()),
        ):
            await run_pipeline(options, source_db=source_db)

        fetch_sources.assert_awaited_once_with(
            ["ca", "uk"],
            limit=7,
            source_db=source_db,
            reporter=None,
        )

    def test_structure_node_omits_original_source_json_from_prompt(self) -> None:
        scraped_record = _scraped_record()
        state: PipelineRecordState = {
            "record": scraped_record,
            "translated_json": {"record": scraped_record.payload},
            "summary": _valid_summary(),
        }

        with patch("agents.graph.chat_json", return_value=_valid_structured_json()) as chat_json:
            structure_node(state)

        user_prompt = chat_json.call_args.kwargs["user_prompt"]
        self.assertIn("translated_source_json", user_prompt)
        self.assertNotIn("original_source_json", user_prompt)

    def test_structure_node_retries_invalid_schema(self) -> None:
        scraped_record = _scraped_record()
        state: PipelineRecordState = {
            "record": scraped_record,
            "translated_json": {"record": scraped_record.payload},
            "summary": "Short summary.",
        }

        with patch(
            "agents.graph.chat_json",
            side_effect=[{"unexpected": "shape"}, _valid_structured_json()],
        ) as chat_json:
            result = structure_node(state)

        self.assertEqual(chat_json.call_count, 2)
        self.assertEqual(result["structured_json"]["product_category"], "Produce")

    def test_structure_node_falls_back_after_retry_failure(self) -> None:
        scraped_record = _scraped_record()
        state: PipelineRecordState = {
            "record": scraped_record,
            "translated_json": {"record": scraped_record.payload},
            "summary": "Short summary.",
        }

        with patch("agents.graph.chat_json", side_effect=[{"unexpected": "shape"}, {"still": "wrong"}]):
            result = structure_node(state)

        structured = result["structured_json"]
        self.assertEqual(structured["web_source"], "uk")
        self.assertEqual(structured["product_name"], "Original Product")
        self.assertEqual(structured["recall_date"], "2026-06-09")
        self.assertEqual(structured["country_source"], "Unknown")

    def test_translate_values_node_falls_back_to_envelope_on_validation_error(self) -> None:
        scraped_record = _scraped_record()
        state: PipelineRecordState = {"record": scraped_record}

        with patch("agents.graph.chat_json", side_effect=AgentValidationError("invalid translation structure")):
            result = translate_values_node(state)

        self.assertEqual(result["translated_json"], {"record": scraped_record.payload})

    def test_translate_values_node_uses_translated_payload_when_valid(self) -> None:
        scraped_record = _scraped_record()
        translated = {
            "record": {
                **scraped_record.payload,
                "headings": ["Produit rappelé Original Product", "Risque", "Action"],
            }
        }
        state: PipelineRecordState = {"record": scraped_record}

        with patch("agents.graph.chat_json", return_value=translated):
            result = translate_values_node(state)

        self.assertEqual(result["translated_json"], translated)

    def test_summarize_node_returns_summary_for_valid_text(self) -> None:
        with patch("agents.graph.chat_text", return_value="Valid summary text."):
            result = summarize_node({"translated_json": {"record": _scraped_record().payload}})
        self.assertEqual(result["summary"], "Valid summary text.")

    def test_summarize_node_raises_on_blank_summary(self) -> None:
        with patch("agents.graph.chat_text", return_value="   "):
            with self.assertRaises(AgentValidationError):
                summarize_node({"translated_json": {"record": _scraped_record().payload}})

    async def test_run_pipeline_raises_when_all_sources_fail_to_fetch(self) -> None:
        options = _options(sources=["us"], limit=1)

        with patch(
            "agents.graph.fetch_sources_sequentially",
            new=AsyncMock(return_value=FetchSourcesResult(records=[], failures={"us": "403"})),
        ):
            with self.assertRaises(SourceFetchError):
                await run_pipeline(options, source_db=_source_db())

    async def test_run_pipeline_keeps_source_failures_when_records_exist(self) -> None:
        options = _options(sources=["uk", "us"], limit=2)
        on_warning = Mock()
        with (
            patch(
                "agents.graph.fetch_sources_sequentially",
                new=AsyncMock(
                    return_value=FetchSourcesResult(records=[_scraped_record("uk")], failures={"us": "Timeout"})
                ),
            ),
            patch("agents.graph.chat_json", side_effect=[{"record": _scraped_record().payload}, _valid_structured_json()]),
            patch("agents.graph.chat_text", return_value=_valid_summary()),
        ):
            result = await run_pipeline(
                options,
                source_db=_source_db(),
                on_warning=on_warning,
                run_id="run-partial",
            )

        self.assertEqual(result.records_fetched, 1)
        self.assertEqual(result.source_failures, {"us": "Timeout"})
        on_warning.assert_called_once_with(
            category="source_skipped",
            message='Source "us" was skipped during scraping: Timeout',
            source="us",
            run_id="run-partial",
        )

    async def test_run_pipeline_returns_empty_when_nothing_fetched_and_no_failures(self) -> None:
        options = _options(sources=["uk"], limit=1)
        with patch(
            "agents.graph.fetch_sources_sequentially",
            new=AsyncMock(return_value=FetchSourcesResult(records=[], failures={})),
        ):
            result = await run_pipeline(options, source_db=_source_db())
        self.assertEqual(result.records_fetched, 0)
        self.assertEqual(result.alerts, [])

    async def test_run_pipeline_skips_records_that_fail_processing(self) -> None:
        fake_graph = AsyncMock()
        fake_graph.ainvoke = AsyncMock(
            side_effect=[ValueError("invalid structured payload"), {"alert": _alert_for_source("ca")}]
        )
        on_warning = Mock()
        with (
            patch(
                "agents.graph.fetch_sources_sequentially",
                new=AsyncMock(return_value=FetchSourcesResult(records=[_scraped_record("uk"), _scraped_record("ca")])),
            ),
            patch("agents.graph.create_pipeline_graph", return_value=fake_graph),
        ):
            result = await run_pipeline(
                _options(["uk", "ca"], limit=2),
                source_db=_source_db(),
                on_warning=on_warning,
                run_id="run-skip",
            )
        self.assertEqual(result.records_fetched, 2)
        self.assertEqual(len(result.alerts), 1)
        self.assertEqual(result.alerts[0].web_source, "ca")
        on_warning.assert_called_once_with(
            category="record_skipped",
            message='Product record from "uk" skipped after pipeline processing failure',
            source="uk",
            run_id="run-skip",
        )

    async def test_run_pipeline_invokes_callback_for_each_processed_alert(self) -> None:
        fake_graph = AsyncMock()
        first_alert = _alert_for_source("uk")
        second_alert = _alert_for_source("ca")
        fake_graph.ainvoke = AsyncMock(side_effect=[{"alert": first_alert}, {"alert": second_alert}])
        on_alert_processed = Mock(return_value=1)

        with (
            patch(
                "agents.graph.fetch_sources_sequentially",
                new=AsyncMock(return_value=FetchSourcesResult(records=[_scraped_record("uk"), _scraped_record("ca")])),
            ),
            patch("agents.graph.create_pipeline_graph", return_value=fake_graph),
        ):
            result = await run_pipeline(
                _options(["uk", "ca"], limit=2),
                source_db=_source_db(),
                on_alert_processed=on_alert_processed,
            )

        self.assertEqual(result.records_fetched, 2)
        self.assertEqual(len(result.alerts), 2)
        self.assertEqual(on_alert_processed.call_count, 2)
        on_alert_processed.assert_any_call(first_alert)
        on_alert_processed.assert_any_call(second_alert)

    async def test_run_pipeline_does_not_invoke_callback_for_failed_record(self) -> None:
        fake_graph = AsyncMock()
        second_alert = _alert_for_source("ca")
        fake_graph.ainvoke = AsyncMock(side_effect=[ValueError("bad record"), {"alert": second_alert}])
        on_alert_processed = Mock(return_value=1)

        with (
            patch(
                "agents.graph.fetch_sources_sequentially",
                new=AsyncMock(return_value=FetchSourcesResult(records=[_scraped_record("uk"), _scraped_record("ca")])),
            ),
            patch("agents.graph.create_pipeline_graph", return_value=fake_graph),
        ):
            result = await run_pipeline(
                _options(["uk", "ca"], limit=2),
                source_db=_source_db(),
                on_alert_processed=on_alert_processed,
            )

        self.assertEqual(result.records_fetched, 2)
        self.assertEqual(len(result.alerts), 1)
        on_alert_processed.assert_called_once_with(second_alert)

def _options(sources: list[str], limit: int) -> PipelineRunOptions:
    return PipelineRunOptions.model_construct(sources=sources, limit=limit)

def _source_db() -> Mock:
    return Mock()

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
        "batch_id": "LOT-ABC-123",
        "country_source": "UK",
        "affected_regions": ["Ontario"],
    }

def _alert_for_source(source: str) -> FoodRecallAlertCreate:
    return FoodRecallAlertCreate(
        web_source=source,
        country_source=web_source_to_country_source(source),
        product_name="Original Product",
        product_category="Produce",
        recall_reason="Possible contamination",
        summary=_valid_summary(),
        recall_date=date(2026, 6, 9),
        risk_level="High",
        hazard_type="Listeria",
        consumer_action="Do not consume it.",
        source_url="https://source.example.com/recalls/abc",
        affected_regions=[],
    )

def _scraped_record(source_name: str = "uk") -> ScrapedRecallRecord:
    return ScrapedRecallRecord(
        source_name=source_name,
        payload={
            "source_url": "https://source.example.com/recalls/abc",
            "headings": ["Original Product", "Risk", "Action"],
            "visible_text": "Original Product recalled due to contamination. Do not consume this product.",
            "selected_recall_date": "2026-06-09",
        },
    )

if __name__ == "__main__":
    unittest.main()
