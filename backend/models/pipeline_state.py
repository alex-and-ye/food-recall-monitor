"""In-graph state shape for processing a single scraped recall record.

TypedDict keys accumulate translation, summary, structured extraction,
and the final alert as the LangGraph pipeline advances.
"""

from typing import Any, TypedDict

from models.food_recall_alert import FoodRecallAlertCreate
from models.scraped_record import ScrapedRecallRecord

class PipelineRecordState(TypedDict, total=False):
    """Partial per-record state carried through agent graph nodes."""

    record: ScrapedRecallRecord
    translated_json: dict[str, Any]
    summary: str
    structured_json: dict[str, Any]
    alert: FoodRecallAlertCreate
