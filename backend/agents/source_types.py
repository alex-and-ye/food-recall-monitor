from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class SourceRecord(BaseModel):
    source: str
    raw_record: dict[str, Any]
    working_json: dict[str, Any]
