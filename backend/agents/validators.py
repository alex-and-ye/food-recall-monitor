"""Validation helpers for agent pipeline intermediate and final outputs.

Ensures translated JSON preserves structure, summaries are non-empty, and
structured recall JSON contains required fields with correct types.
"""

from typing import Any

# Fields required in structuring agent output before alert conversion.
REQUIRED_STRUCTURED_FIELDS: set[str] = {
    "product_name",
    "product_category",
    "recall_reason",
    "summary",
    "recall_date",
    "risk_level",
    "hazard_type",
    "consumer_action",
    "source_url",
    "batch_id",
    "country_source",
    "affected_regions",
}


class AgentValidationError(ValueError):
    """Raised when agent output fails structural or content validation."""


def validate_translated_structure(original: dict[str, Any], translated: dict[str, Any]) -> None:
    """Verify translation preserved JSON key structure and value types.

    Args:
        original: Source JSON before translation.
        translated: JSON returned by the translation agent.

    Raises:
        AgentValidationError: If keys, nesting, or list/dict shapes differ.
    """
    if _structure_signature(original) != _structure_signature(translated):
        raise AgentValidationError("Translation step changed the JSON key set or structure")


def validate_summary(summary: str) -> None:
    """Verify the summarization step returned non-empty text.

    Args:
        summary: Plain-text summary from the summarization agent.

    Raises:
        AgentValidationError: If the summary is empty or whitespace-only.
    """
    text = summary.strip()
    if not text:
        raise AgentValidationError("Summarization step returned an empty summary")


def validate_structured_json(structured_json: dict[str, Any]) -> None:
    """Verify structuring output contains required fields with valid types.

    Args:
        structured_json: JSON object from the structuring agent.

    Raises:
        AgentValidationError: If required fields are missing, ``alert_id`` is
            present, or ``affected_regions`` is not a list.
    """
    missing_fields = REQUIRED_STRUCTURED_FIELDS.difference(structured_json)
    if missing_fields:
        fields = ", ".join(sorted(missing_fields))
        raise AgentValidationError(f"Structuring step output is missing required fields: {fields}")

    if "alert_id" in structured_json:
        raise AgentValidationError("Structuring step must not return alert_id")

    if not isinstance(structured_json.get("affected_regions"), list):
        raise AgentValidationError("Structuring step affected_regions must be a list")


def _structure_signature(value: Any) -> Any:
    """Build a comparable signature of JSON shape (keys and container types)."""
    if isinstance(value, dict):
        return {
            key: _structure_signature(value[key])
            for key in sorted(value)
        }
    if isinstance(value, list):
        return [_structure_signature(item) for item in value]
    return type(value)
