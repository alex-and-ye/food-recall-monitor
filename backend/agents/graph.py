from __future__ import annotations

import json

from langgraph.graph import END, START, StateGraph

from agents.converters import structured_json_to_alert_create
from agents.fetchers import fetch_sources_sequentially
from agents.llm import AgentOutputError, chat_json, chat_text
from agents.prompts import AGENT1_SYSTEM, AGENT2_SYSTEM, AGENT3_SYSTEM
from agents.state import PipelineRecordState
from agents.validators import (
    AgentValidationError,
    validate_structured_json,
    validate_summary,
    validate_translated_structure,
)
from models.food_recall_alert import FoodRecallAlertCreate
from models.pipeline_options import PipelineRunOptions

AGENT3_MAX_ATTEMPTS = 2


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


async def run_pipeline(options: PipelineRunOptions) -> list[FoodRecallAlertCreate]:
    graph = create_pipeline_graph()
    source_records = await fetch_sources_sequentially(
        options.sources,
        limit=options.limit,
    )

    alerts: list[FoodRecallAlertCreate] = []
    for record in source_records:
        try:
            result = await graph.ainvoke({"record": record})
        except (AgentOutputError, AgentValidationError, ValueError):
            continue
        alerts.append(result["alert"])

    return alerts


def translate_values_node(state: PipelineRecordState) -> PipelineRecordState:
    record = state["record"]
    try:
        translated_json = chat_json(
            system_prompt=AGENT1_SYSTEM,
            user_prompt=json.dumps(record.working_json, ensure_ascii=False),
        )
        validate_translated_structure(record.working_json, translated_json)
    except (AgentOutputError, AgentValidationError):
        translated_json = record.working_json

    return {"translated_json": translated_json}


def summarize_node(state: PipelineRecordState) -> PipelineRecordState:
    record = state["record"]
    user_prompt = json.dumps(
        {
            "protected_fields": record.protected_fields.as_prompt_data(),
            "translated_json": state["translated_json"],
        },
        ensure_ascii=False,
    )
    summary = chat_text(system_prompt=AGENT2_SYSTEM, user_prompt=user_prompt)
    validate_summary(summary)
    return {"summary": summary}


def structure_node(state: PipelineRecordState) -> PipelineRecordState:
    record = state["record"]
    user_prompt_data = {
        "text_summary": state["summary"],
        "protected_fields": record.protected_fields.as_prompt_data(),
        "translated_source_json": state["translated_json"],
    }
    last_error: Exception | None = None

    for attempt in range(AGENT3_MAX_ATTEMPTS):
        user_prompt = json.dumps(user_prompt_data, ensure_ascii=False)
        if attempt > 0 and last_error is not None:
            user_prompt = (
                f"{user_prompt}\n\n"
                "Your previous response could not be used because: "
                f"{last_error}. Return one JSON object matching the exact schema."
            )

        try:
            structured_json = chat_json(
                system_prompt=AGENT3_SYSTEM,
                user_prompt=user_prompt,
            )
            validate_structured_json(structured_json)
            return {"structured_json": structured_json}
        except (AgentOutputError, AgentValidationError) as exc:
            last_error = exc

    return {"structured_json": _fallback_structured_json(state)}


def _fallback_structured_json(state: PipelineRecordState) -> dict[str, object]:
    record = state["record"]
    protected_fields = record.protected_fields

    return {
        "product_name": protected_fields.product_name,
        "product_category": "Other",
        "recall_reason": _source_text(record.working_json, "recall_reason", "Recall reason unavailable"),
        "summary": state["summary"],
        "recall_date": protected_fields.recall_date.isoformat(),
        "risk_level": "Unknown",
        "hazard_type": _source_text(record.working_json, "hazard_type", "Unknown"),
        "consumer_action": _source_text(record.working_json, "consumer_action", "Follow the source recall notice."),
        "source_url": protected_fields.source_url,
        "affected_regions": _source_regions(record.working_json),
    }


def _source_text(data: dict[str, object], key: str, default: str) -> str:
    value = data.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


def _source_regions(data: dict[str, object]) -> list[str]:
    value = data.get("affected_regions")
    if not isinstance(value, list):
        return []

    return [
        str(item).strip()
        for item in value
        if str(item).strip()
    ]


def repair_and_convert_node(state: PipelineRecordState) -> PipelineRecordState:
    record = state["record"]
    structured_json = dict(state["structured_json"])
    protected_fields = record.protected_fields

    structured_json["product_name"] = protected_fields.product_name
    structured_json["recall_date"] = protected_fields.recall_date.isoformat()
    structured_json["source_url"] = protected_fields.source_url
    structured_json["summary"] = state["summary"]

    alert = structured_json_to_alert_create(structured_json)
    return {"structured_json": structured_json, "alert": alert}
