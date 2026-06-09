from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel

from models.pipeline_options import RecallSource


class ProtectedFields(BaseModel):
    product_name: str
    recall_date: date
    source_url: str

    def as_prompt_data(self) -> dict[str, str]:
        return {
            "product_name": self.product_name,
            "recall_date": self.recall_date.isoformat(),
            "source_url": self.source_url,
        }


class SourceRecord(BaseModel):
    source: RecallSource
    raw_record: dict[str, Any]
    protected_fields: ProtectedFields
    working_json: dict[str, Any]
