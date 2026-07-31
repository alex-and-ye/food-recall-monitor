from typing import Any, TypedDict

from models.food_recall_alert import FoodRecallAlertCreate
from models.scraped_record import ScrapedRecallRecord

class PipelineRecordState(TypedDict, total=False):
    record: ScrapedRecallRecord
    translated_json: dict[str, Any]
    summary: str
    structured_json: dict[str, Any]
    alert: FoodRecallAlertCreate
