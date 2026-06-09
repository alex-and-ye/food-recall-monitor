from __future__ import annotations

import re
from typing import Any


REQUIRED_STRUCTURED_FIELDS = {
    "product_name",
    "product_category",
    "recall_reason",
    "summary",
    "recall_date",
    "risk_level",
    "hazard_type",
    "consumer_action",
    "source_url",
    "affected_regions",
}

_PREAMBLE_PATTERN = re.compile(
    r"^\s*(here\s+(is|are)\b|sure\b|summary\s*:|below\s+is\b).*?(:|\n)",
    re.IGNORECASE | re.DOTALL,
)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


class AgentValidationError(ValueError):
    pass


def validate_translated_structure(original: dict[str, Any], translated: dict[str, Any]) -> None:
    if _structure_signature(original) != _structure_signature(translated):
        raise AgentValidationError("Agent 1 changed the JSON key set or structure")


def validate_summary(summary: str) -> None:
    text = summary.strip()
    if not text:
        raise AgentValidationError("Agent 2 returned an empty summary")

    first_line = text.splitlines()[0]
    if _PREAMBLE_PATTERN.match(first_line):
        raise AgentValidationError("Agent 2 returned a summary preamble")

    sentences = [sentence for sentence in _SENTENCE_SPLIT.split(text) if sentence.strip()]
    if len(sentences) != 3:
        raise AgentValidationError("Agent 2 summary must contain exactly three sentences")


def validate_structured_json(structured_json: dict[str, Any]) -> None:
    missing_fields = REQUIRED_STRUCTURED_FIELDS.difference(structured_json)
    if missing_fields:
        fields = ", ".join(sorted(missing_fields))
        raise AgentValidationError(f"Agent 3 output is missing required fields: {fields}")

    if "alert_id" in structured_json:
        raise AgentValidationError("Agent 3 must not return alert_id")

    if not isinstance(structured_json.get("affected_regions"), list):
        raise AgentValidationError("Agent 3 affected_regions must be a list")


def _structure_signature(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _structure_signature(value[key])
            for key in sorted(value)
        }
    if isinstance(value, list):
        return [_structure_signature(item) for item in value]
    return type(value)
