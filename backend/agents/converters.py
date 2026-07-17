from __future__ import annotations

from typing import Any

from agents.normalizers.protected_fields import clean_text, parse_source_date
from agents.validators import validate_structured_json
from models.food_recall_alert import FoodRecallAlertCreate

def structured_json_to_alert_create(
    structured_json: dict[str, Any],
) -> FoodRecallAlertCreate:
    validate_structured_json(structured_json)

    web_source = _required_text(structured_json, "web_source")

    return FoodRecallAlertCreate(
        web_source=web_source,
        country_source=_required_text(structured_json, "country_source"),
        product_name=_required_text(structured_json, "product_name"),
        product_category=_optional_text(structured_json, "product_category", "Other"),
        recall_reason=_required_text(structured_json, "recall_reason"),
        summary=_required_text(structured_json, "summary"),
        recall_date=parse_source_date(structured_json["recall_date"]),
        risk_level=_optional_text(structured_json, "risk_level", "Unknown"),
        hazard_type=_required_text(structured_json, "hazard_type"),
        consumer_action=_required_text(structured_json, "consumer_action"),
        source_url=_required_text(structured_json, "source_url"),
        batch_id=clean_text(str(structured_json.get("batch_id", ""))),
        affected_regions=_string_list(structured_json.get("affected_regions")),
    )

def _required_text(data: dict[str, Any], key: str) -> str:
    value = clean_text(str(data.get(key, "")))
    if not value:
        raise ValueError(f"Missing required field: {key}")
    return value

def _optional_text(data: dict[str, Any], key: str, default: str) -> str:
    value = clean_text(str(data.get(key, "")))
    return value or default

def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []

    return [
        clean_text(str(item))
        for item in value
        if clean_text(str(item))
    ]
