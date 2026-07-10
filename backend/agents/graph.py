from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from langgraph.graph import END, START, StateGraph

from agents.converters import structured_json_to_alert_create
from agents.errors import SourceFetchError
from agents.fetchers import fetch_sources_sequentially, to_translator_envelope
from agents.llm import AgentOutputError, chat_json, chat_text
from agents.normalizers.protected_fields import clean_text, parse_source_date
from agents.prompts import (
    STRUCTURING_SYSTEM_PROMPT,
    SUMMARIZATION_SYSTEM_PROMPT,
    TRANSLATION_SYSTEM_PROMPT,
)
from agents.validators import (
    AgentValidationError,
    validate_structured_json,
    validate_summary,
    validate_translated_structure,
)
from config.agents import TRANSLATION_MODEL
from models.food_recall_alert import FoodRecallAlertCreate
from models.pipeline_options import PipelineRunOptions
from models.pipeline_progress import ProgressReporter
from models.pipeline_result import AgentPipelineResult
from models.pipeline_state import PipelineRecordState

LOGGER: logging.Logger = logging.getLogger(__name__)

STRUCTURING_AGENT_MAX_ATTEMPTS: int = 2

def create_pipeline_graph(*, reporter: ProgressReporter | None = None):
    graph = StateGraph(PipelineRecordState)
    graph.add_node(
        "translate_values",
        _tracked_node("translate_values", translate_values_node, reporter),
    )
    graph.add_node(
        "summarize",
        _tracked_node("summarize", summarize_node, reporter),
    )
    graph.add_node(
        "structure",
        _tracked_node("structure", structure_node, reporter),
    )
    graph.add_node(
        "repair_and_convert",
        _tracked_node("repair_and_convert", repair_and_convert_node, reporter),
    )

    graph.add_edge(START, "translate_values")
    graph.add_edge("translate_values", "summarize")
    graph.add_edge("summarize", "structure")
    graph.add_edge("structure", "repair_and_convert")
    graph.add_edge("repair_and_convert", END)

    return graph.compile()

async def run_pipeline(
    options: PipelineRunOptions,
    *,
    reporter: ProgressReporter | None = None,
    on_alert_processed: Callable[[FoodRecallAlertCreate], int] | None = None,
) -> AgentPipelineResult:
    graph = create_pipeline_graph(reporter=reporter)
    if reporter is not None:
        reporter.log(
            stage="fetch",
            message="Starting source fetch",
            details={"sources": options.sources, "limit": options.limit},
        )
        fetch_result = await fetch_sources_sequentially(
            options.sources,
            limit=options.limit,
            reporter=reporter,
        )
    else:
        fetch_result = await fetch_sources_sequentially(
            options.sources,
            limit=options.limit,
        )

    if not fetch_result.records and fetch_result.failures:
        raise SourceFetchError(fetch_result.failures)

    if reporter is not None:
        reporter.log(
            stage="fetch",
            message="Source fetch completed",
            details={
                "records_fetched": len(fetch_result.records),
                "source_failures": fetch_result.failures,
                "fetched_records": [
                    {
                        "source_name": record.source_name,
                        "payload": _to_jsonable(record.payload),
                    }
                    for record in fetch_result.records
                ],
            },
        )

    alerts: list[FoodRecallAlertCreate] = []
    for index, record in enumerate(fetch_result.records, start=1):
        if reporter is not None:
            reporter.log(
                stage="record",
                source=record.source_name,
                message="Processing scraped record",
                details={
                    "record_index": index,
                    "source_url": record.payload.get("source_url", ""),
                    "record_payload": _to_jsonable(record.payload),
                },
            )
        try:
            result = await graph.ainvoke({"record": record})
        except (AgentOutputError, AgentValidationError, ValueError) as exc:
            LOGGER.warning(
                "Skipping record from %s after pipeline failure: %s",
                record.source_name,
                exc,
            )
            if reporter is not None:
                reporter.log(
                    stage="record",
                    source=record.source_name,
                    message="Record processing failed",
                    details={
                        "record_index": index,
                        "error": str(exc),
                        "record_payload": _to_jsonable(record.payload),
                    },
                )
            continue
        alerts.append(result["alert"])
        if on_alert_processed is not None:
            on_alert_processed(result["alert"])
        if reporter is not None:
            reporter.log(
                stage="record",
                source=record.source_name,
                message="Record processed successfully",
                details={
                    "record_index": index,
                    "processed_state": _state_snapshot(result),
                },
            )

    return AgentPipelineResult(
        alerts=alerts,
        records_fetched=len(fetch_result.records),
        source_failures=fetch_result.failures,
    )


def _tracked_node(
    node_name: str,
    node_fn: Callable[[PipelineRecordState], PipelineRecordState],
    reporter: ProgressReporter | None,
) -> Callable[[PipelineRecordState], PipelineRecordState]:
    def wrapped(state: PipelineRecordState) -> PipelineRecordState:
        source_name = None
        if "record" in state:
            source_name = state["record"].source_name
        if reporter is not None:
            reporter.log(
                stage="agent",
                source=source_name,
                message=f"{node_name} started",
                details={"input_state": _state_snapshot(state)},
            )
        result = node_fn(state)
        if reporter is not None:
            reporter.log(
                stage="agent",
                source=source_name,
                message=f"{node_name} completed",
                details={"output_state": _state_snapshot(result)},
            )
        return result

    return wrapped

def translate_values_node(state: PipelineRecordState) -> PipelineRecordState:
    if "record" not in state:
        raise ValueError("Pipeline state is missing required key: record")
    record = state["record"]
    translator_input = to_translator_envelope(record.payload)
    try:
        translated_json = chat_json(
            system_prompt=TRANSLATION_SYSTEM_PROMPT,
            user_prompt=json.dumps(translator_input, ensure_ascii=False),
            model=TRANSLATION_MODEL,
        )
        validate_translated_structure(translator_input, translated_json)
    except (AgentOutputError, AgentValidationError) as exc:
        LOGGER.warning(
            "Translation step failed for %s, using original record JSON: %s",
            record.source_name,
            exc,
        )
        translated_json = translator_input

    return {"translated_json": translated_json}

def summarize_node(state: PipelineRecordState) -> PipelineRecordState:
    if "translated_json" not in state:
        raise ValueError("Pipeline state is missing required key: translated_json")
    user_prompt = json.dumps(
        {
            "translated_json": state["translated_json"],
        },
        ensure_ascii=False,
    )
    summary = chat_text(system_prompt=SUMMARIZATION_SYSTEM_PROMPT, user_prompt=user_prompt)
    validate_summary(summary)
    return {"summary": summary}

def structure_node(state: PipelineRecordState) -> PipelineRecordState:
    if "record" not in state:
        raise ValueError("Pipeline state is missing required key: record")
    if "summary" not in state:
        raise ValueError("Pipeline state is missing required key: summary")
    if "translated_json" not in state:
        raise ValueError("Pipeline state is missing required key: translated_json")
    record = state["record"]
    user_prompt_data = {
        "text_summary": state["summary"],
        "translated_source_json": state["translated_json"],
    }
    last_error: Exception | None = None

    for attempt in range(STRUCTURING_AGENT_MAX_ATTEMPTS):
        user_prompt = json.dumps(user_prompt_data, ensure_ascii=False)
        if attempt > 0 and last_error is not None:
            user_prompt = (
                f"{user_prompt}\n\n"
                "Your previous response could not be used because: "
                f"{last_error}. Return one JSON object matching the exact schema."
            )

        try:
            structured_json = chat_json(
                system_prompt=STRUCTURING_SYSTEM_PROMPT,
                user_prompt=user_prompt,
            )
            validate_structured_json(structured_json)
            return {"structured_json": structured_json}
        except (AgentOutputError, AgentValidationError) as exc:
            last_error = exc

    return {"structured_json": _fallback_structured_json(state)}

def _fallback_structured_json(state: PipelineRecordState) -> dict[str, object]:
    if "record" not in state:
        raise ValueError("Pipeline state is missing required key: record")
    if "summary" not in state:
        raise ValueError("Pipeline state is missing required key: summary")
    record = state["record"]

    return {
        "api_source": record.source_name,
        "product_name": _best_payload_value("product_name", "", record.payload),
        "product_category": "Other",
        "recall_reason": "Recall reason unavailable",
        "summary": state["summary"],
        "recall_date": _best_payload_value("recall_date", "", record.payload),
        "risk_level": "Unknown",
        "hazard_type": "Unknown",
        "consumer_action": "Follow the source recall notice.",
        "source_url": _best_payload_value("source_url", "", record.payload),
        "affected_regions": [],
    }

def repair_and_convert_node(state: PipelineRecordState) -> PipelineRecordState:
    if "record" not in state:
        raise ValueError("Pipeline state is missing required key: record")
    if "structured_json" not in state:
        raise ValueError("Pipeline state is missing required key: structured_json")
    if "summary" not in state:
        raise ValueError("Pipeline state is missing required key: summary")
    record = state["record"]
    structured_json = {
        "api_source": record.source_name,
        **{
            key: value
            for key, value in dict(state["structured_json"]).items()
            if key != "api_source"
        },
    }

    structured_json["product_name"] = _best_generated_product_name(
        structured_json.get("product_name"),
        record.payload,
    )
    structured_json["recall_date"] = _best_generated_recall_date(
        structured_json.get("recall_date"),
        record.payload,
    )
    structured_json["source_url"] = _best_payload_value(
        "source_url",
        structured_json.get("source_url"),
        record.payload,
    )
    structured_json["summary"] = state["summary"]

    alert = structured_json_to_alert_create(structured_json)
    return {"structured_json": structured_json, "alert": alert}


def _best_payload_value(field_name: str, generated_value: Any, payload: dict[str, Any]) -> str:
    fields = _original_string_fields(payload)
    generated_text = clean_text(str(generated_value or ""))

    exact_match = _exact_original_match(generated_text, fields)
    if exact_match:
        return exact_match

    if field_name == "source_url":
        return _best_source_url(fields) or generated_text
    if field_name == "recall_date":
        return _best_recall_date(generated_text, fields) or generated_text
    if field_name == "product_name":
        return _best_product_name(generated_text, fields) or generated_text
    return generated_text

def _best_generated_product_name(generated_value: Any, payload: dict[str, Any]) -> str:
    fields = _original_string_fields(payload)
    generated_text = clean_text(str(generated_value or ""))

    exact_match = _exact_original_match(generated_text, fields)
    if exact_match:
        return exact_match
    if generated_text:
        return generated_text
    return _best_product_name("", fields)

def _best_generated_recall_date(generated_value: Any, payload: dict[str, Any]) -> str:
    generated_text = clean_text(str(generated_value or ""))
    if payload.get("selected_recall_date_source") == "generic" and _safe_parse_date(generated_text) is not None:
        return generated_text
    return _best_payload_value("recall_date", generated_value, payload)

def _exact_original_match(value: str, fields: list[tuple[str, str]]) -> str:
    if not value:
        return ""
    for _, original_value in fields:
        if clean_text(original_value) == value:
            return original_value
    return ""

def _best_source_url(fields: list[tuple[str, str]]) -> str:
    candidates = [
        (path, value)
        for path, value in fields
        if value.strip().lower().startswith(("http://", "https://"))
    ]
    if not candidates:
        return ""

    def score(candidate: tuple[str, str]) -> int:
        path, _ = candidate
        lowered_path = path.lower()
        return (
            120 * ("source_url" in lowered_path)
            + 100 * ("url" in lowered_path)
            + 60 * ("link" in lowered_path or "lien" in lowered_path)
            + 30 * ("source" in lowered_path)
        )

    return max(candidates, key=score)[1]

def _best_recall_date(generated_value: str, fields: list[tuple[str, str]]) -> str:
    generated_date = _safe_parse_date(generated_value)
    candidates = [
        (path, value, _safe_parse_date(value))
        for path, value in fields
        if _safe_parse_date(value) is not None
    ]
    if not candidates:
        return ""

    if generated_date is not None:
        for _, value, candidate_date in candidates:
            if candidate_date == generated_date:
                return value

    def score(candidate: tuple[str, str, object]) -> int:
        path, _, _ = candidate
        lowered_path = path.lower()
        return (
            160 * ("selected_recall_date" in lowered_path)
            + 100 * ("recall" in lowered_path or "rappel" in lowered_path)
            + 80 * ("publication" in lowered_path or "created" in lowered_path)
            + 40 * ("date" in lowered_path)
            - 60 * ("end" in lowered_path or "fin" in lowered_path or "closed" in lowered_path)
        )

    return max(candidates, key=score)[1]

def _safe_parse_date(value: str):
    try:
        return parse_source_date(value)
    except ValueError:
        return None

def _best_product_name(generated_value: str, fields: list[tuple[str, str]]) -> str:
    candidates = [
        (path, value)
        for path, value in fields
        if value.strip() and not value.strip().lower().startswith(("http://", "https://"))
    ]
    if not candidates:
        return ""

    def score(candidate: tuple[str, str]) -> int:
        path, value = candidate
        lowered_path = path.lower()
        lowered_value = clean_text(value).lower()
        lowered_generated = generated_value.lower()
        return (
            180 * ("headings" in lowered_path)
            + 120 * ("heading" in lowered_path)
            + 110 * ("productname" in lowered_path or "product_name" in lowered_path)
            + 80 * ("product" in lowered_path or "produit" in lowered_path)
            + 40 * ("model" in lowered_path or "reference" in lowered_path)
            + 20 * ("brand" in lowered_path or "marque" in lowered_path or "establishment" in lowered_path)
            + 80 * bool(lowered_generated and lowered_generated in lowered_value)
            + 80 * bool(lowered_generated and lowered_value in lowered_generated)
            - 120 * ("visible_text" in lowered_path)
            - 90 * ("summary" in lowered_path or "description" in lowered_path or "advice" in lowered_path)
            - max(len(value) - 180, 0)
        )

    return max(candidates, key=score)[1]

def _original_string_fields(value: Any, path: str = "") -> list[tuple[str, str]]:
    if isinstance(value, str):
        return [(path, value)] if value.strip() else []
    if isinstance(value, dict):
        fields: list[tuple[str, str]] = []
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            fields.extend(_original_string_fields(child, child_path))
        return fields
    if isinstance(value, list):
        fields = []
        for index, child in enumerate(value):
            fields.extend(_original_string_fields(child, f"{path}[{index}]"))
        return fields
    return []


def _state_snapshot(state: dict[str, Any]) -> dict[str, Any]:
    snapshot: dict[str, Any] = {}
    if "record" in state:
        record = state["record"]
        snapshot["record"] = {
            "source_name": record.source_name,
            "payload": _to_jsonable(record.payload),
        }
    if "translated_json" in state:
        snapshot["translated_json"] = _to_jsonable(state["translated_json"])
    if "summary" in state:
        snapshot["summary"] = _to_jsonable(state["summary"])
    if "structured_json" in state:
        snapshot["structured_json"] = _to_jsonable(state["structured_json"])
    if "alert" in state:
        snapshot["alert"] = _to_jsonable(state["alert"])
    return snapshot


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(key): _to_jsonable(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(child) for child in value]
    if isinstance(value, tuple):
        return [_to_jsonable(child) for child in value]
    if isinstance(value, set):
        return [_to_jsonable(child) for child in sorted(value, key=str)]
    if hasattr(value, "model_dump"):
        try:
            return _to_jsonable(value.model_dump(mode="json"))
        except TypeError:
            return _to_jsonable(value.model_dump())
    return str(value)
