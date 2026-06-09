from __future__ import annotations

import json

from langgraph.graph import END, START, StateGraph

from agents.converters import structured_json_to_alert_create
from agents.fetchers import fetch_sources_sequentially
from agents.llm import chat_json, chat_text
from agents.prompts import AGENT1_SYSTEM, AGENT2_SYSTEM, AGENT3_SYSTEM
from agents.state import PipelineRecordState
from agents.validators import (
    validate_structured_json,
    validate_summary,
    validate_translated_structure,
)
from models.pipeline_options import PipelineRunOptions
from models.recall_alert import FoodRecallAlertCreate


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
        result = await graph.ainvoke({"record": record})
        alerts.append(result["alert"])

    return alerts


def translate_values_node(state: PipelineRecordState) -> PipelineRecordState:
    record = state["record"]
    translated_json = chat_json(
        system_prompt=AGENT1_SYSTEM,
        user_prompt=json.dumps(record.working_json, ensure_ascii=False),
    )
    validate_translated_structure(record.working_json, translated_json)
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
    user_prompt = json.dumps(
        {
            "text_summary": state["summary"],
            "protected_fields": record.protected_fields.as_prompt_data(),
            "translated_source_json": state["translated_json"],
        },
        ensure_ascii=False,
    )
    structured_json = chat_json(
        system_prompt=AGENT3_SYSTEM,
        user_prompt=user_prompt,
    )
    validate_structured_json(structured_json)
    return {"structured_json": structured_json}


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
