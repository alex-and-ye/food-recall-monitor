from __future__ import annotations

from typing import Any, TypedDict

from agents.source_types import SourceRecord
from models.food_recall_alert import FoodRecallAlertCreate


class PipelineRecordState(TypedDict, total=False):
    record: SourceRecord
    translated_json: dict[str, Any]
    summary: str
    structured_json: dict[str, Any]
    alert: FoodRecallAlertCreate
