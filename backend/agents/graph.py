from __future__ import annotations

import json
from typing import Any

from langgraph.graph import END, START, StateGraph

from agents.fetchers import fetch_sources_sequentially
from agents.llm import chat_json, chat_text
from agents.prompts import AGENT1_SYSTEM, AGENT2_SYSTEM, AGENT3_SYSTEM
from agents.source_types import SourceRecord
from agents.state import PipelineRecordState
from models.pipeline_options import PipelineRunOptions


def create_pipeline_graph():
    graph = StateGraph(PipelineRecordState)
    graph.add_node("translate_values", translate_values_node)
    graph.add_node("summarize", summarize_node)
    graph.add_node("structure", structure_node)
    graph.add_node("repair_protected_fields", repair_protected_fields_node)

    graph.add_edge(START, "translate_values")
    graph.add_edge("translate_values", "summarize")
    graph.add_edge("summarize", "structure")
    graph.add_edge("structure", "repair_protected_fields")
    graph.add_edge("repair_protected_fields", END)

    return graph.compile()


async def run_pipeline(options: PipelineRunOptions) -> list[dict[str, Any]]:
    graph = create_pipeline_graph()
    source_records = await fetch_sources_sequentially(
        options.sources,
        limit=options.limit,
    )

    structured_records: list[dict[str, Any]] = []
    for record in source_records:
        result = await graph.ainvoke({"record": record})
        structured_records.append(result["structured_json"])

    return structured_records


def translate_values_node(state: PipelineRecordState) -> PipelineRecordState:
    record = state["record"]
    translated_json = chat_json(
        system_prompt=AGENT1_SYSTEM,
        user_prompt=json.dumps(record.working_json, ensure_ascii=False),
    )
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
    return {"structured_json": structured_json}


def repair_protected_fields_node(state: PipelineRecordState) -> PipelineRecordState:
    record = state["record"]
    structured_json = dict(state["structured_json"])
    protected_fields = record.protected_fields

    structured_json["product_name"] = protected_fields.product_name
    structured_json["recall_date"] = protected_fields.recall_date.isoformat()
    structured_json["source_url"] = protected_fields.source_url
    structured_json["summary"] = state["summary"]

    return {"structured_json": structured_json}
