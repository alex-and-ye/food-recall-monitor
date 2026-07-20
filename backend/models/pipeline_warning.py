from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class WarningCategory(StrEnum):
    SOURCE_SKIPPED = "source_skipped"
    RECORD_SKIPPED = "record_skipped"
    PIPELINE_FAILED = "pipeline_failed"

WARNING_CATEGORIES: frozenset[str] = frozenset(WarningCategory)

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
