from __future__ import annotations

import json
import logging
from typing import Any

from langgraph.graph import END, START, StateGraph

from agents.converters import structured_json_to_alert_create
from agents.errors import SourceFetchError
from agents.fetchers import fetch_sources_sequentially
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
from agents.config import TRANSLATION_MODEL
from models.food_recall_alert import FoodRecallAlertCreate
from models.pipeline_options import PipelineRunOptions
from models.pipeline_result import AgentPipelineResult
from models.pipeline_state import PipelineRecordState

LOGGER = logging.getLogger(__name__)

STRUCTURING_AGENT_MAX_ATTEMPTS: int = 2

def create_pipeline_graph():
    graph = StateGraph(PipelineRecordState)
    graph.add_node("translate_values", translate_values_node)
    graph.add_node("summarize", summarize_node)
    graph.add_node("structure", structure_node)
    graph.add_node("repair_and_convert", repair_and_convert_node)

    graph.add_edge(START, "translate_values")
    graph.add_edge("translate_values", "summarize")
    graph.add_edge("summarize", "structure")
    graph.add_edge("structure", "repair_and_convert")
    graph.add_edge("repair_and_convert", END)

    return graph.compile()

async def run_pipeline(options: PipelineRunOptions) -> AgentPipelineResult:
    graph = create_pipeline_graph()
    fetch_result = await fetch_sources_sequentially(
        options.sources,
        limit=options.limit,
    )

    if not fetch_result.records and fetch_result.failures:
        raise SourceFetchError(fetch_result.failures)

    alerts: list[FoodRecallAlertCreate] = []
    for record in fetch_result.records:
        try:
            result = await graph.ainvoke({"record": record})
        except (AgentOutputError, AgentValidationError, ValueError) as exc:
            LOGGER.warning(
                "Skipping record from %s after pipeline failure: %s",
                record.source,
                exc,
            )
            continue
        alerts.append(result["alert"])

    return AgentPipelineResult(
        alerts=alerts,
        records_fetched=len(fetch_result.records),
        source_failures=fetch_result.failures,
    )

def translate_values_node(state: PipelineRecordState) -> PipelineRecordState:
    record = state["record"]
    try:
        translated_json = chat_json(
            system_prompt=TRANSLATION_SYSTEM_PROMPT,
            user_prompt=json.dumps(record.working_json, ensure_ascii=False),
            model=TRANSLATION_MODEL,
        )
        validate_translated_structure(record.working_json, translated_json)
    except (AgentOutputError, AgentValidationError) as exc:
        LOGGER.warning(
            "Translation step failed for %s, using original record JSON: %s",
            record.source,
            exc,
        )
        translated_json = record.working_json

    return {"translated_json": translated_json}

def summarize_node(state: PipelineRecordState) -> PipelineRecordState:
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
    record = state["record"]
    user_prompt_data = {
        "text_summary": state["summary"],
        "translated_source_json": state["translated_json"],
        "original_source_json": record.raw_record,
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
    record = state["record"]

    return {
        "api_source": record.source,
        "product_name": _best_original_value("product_name", "", record.raw_record),
        "product_category": "Other",
        "recall_reason": "Recall reason unavailable",
        "summary": state["summary"],
        "recall_date": _best_original_value("recall_date", "", record.raw_record),
        "risk_level": "Unknown",
        "hazard_type": "Unknown",
        "consumer_action": "Follow the source recall notice.",
        "source_url": _best_original_value("source_url", "", record.raw_record),
        "affected_regions": [],
    }

def repair_and_convert_node(state: PipelineRecordState) -> PipelineRecordState:
    record = state["record"]
    structured_json = {
        "api_source": record.source,
        **{
            key: value
            for key, value in dict(state["structured_json"]).items()
            if key != "api_source"
        },
    }

    structured_json["product_name"] = _best_original_value(
        "product_name",
        structured_json.get("product_name"),
        record.raw_record,
    )
    structured_json["recall_date"] = _best_original_value(
        "recall_date",
        structured_json.get("recall_date"),
        record.raw_record,
    )
    structured_json["source_url"] = _best_original_value(
        "source_url",
        structured_json.get("source_url"),
        record.raw_record,
    )
    structured_json["summary"] = state["summary"]

    alert = structured_json_to_alert_create(structured_json)
    return {"structured_json": structured_json, "alert": alert}

def _best_original_value(field_name: str, generated_value: Any, raw_record: dict[str, Any]) -> str:
    fields = _original_string_fields(raw_record)
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
            100 * ("url" in lowered_path)
            + 80 * ("link" in lowered_path or "lien" in lowered_path)
            + 40 * ("fiche" in lowered_path or "recall" in lowered_path)
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
            100 * ("recall" in lowered_path or "rappel" in lowered_path)
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
            120 * ("productname" in lowered_path or "product_name" in lowered_path)
            + 100 * ("libelle" in lowered_path or "title" in lowered_path)
            + 80 * ("product" in lowered_path or "produit" in lowered_path)
            + 50 * ("model" in lowered_path or "reference" in lowered_path)
            + 25 * ("brand" in lowered_path or "marque" in lowered_path or "establishment" in lowered_path)
            + 80 * bool(lowered_generated and lowered_generated in lowered_value)
            + 80 * bool(lowered_generated and lowered_value in lowered_generated)
            - 100 * ("summary" in lowered_path or "description" in lowered_path or "advice" in lowered_path)
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
