from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

WarningCategory = Literal["source_skipped", "record_skipped", "pipeline_failed"]

MAX_WARNINGS_RETAINED = 200
MAX_WARNING_MESSAGE_LENGTH = 280


class PipelineWarning(BaseModel):
    warning_id: str
    created_at: datetime
    category: WarningCategory
    message: str = Field(min_length=1, max_length=MAX_WARNING_MESSAGE_LENGTH)
    source: str | None = None
    acknowledged: bool = False
    run_id: str | None = None


class PipelineWarningCreate(BaseModel):
    category: WarningCategory
    message: str = Field(min_length=1, max_length=MAX_WARNING_MESSAGE_LENGTH)
    source: str | None = None
    run_id: str | None = None


class PipelineWarningsSummary(BaseModel):
    unacknowledged_count: int
