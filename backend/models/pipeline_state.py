from __future__ import annotations

from typing import Any, TypedDict

from models.food_recall_alert import FoodRecallAlertCreate
from models.source_record import SourceRecord

class PipelineRecordState(TypedDict, total=False):
    record: SourceRecord
    translated_json: dict[str, Any]
    summary: str
    structured_json: dict[str, Any]
    alert: FoodRecallAlertCreate
