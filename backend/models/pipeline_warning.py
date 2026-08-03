"""Pipeline warning models for operator-facing run issues.

Captures skip/failure categories from official and early-warning pipelines
with retention limits for the warnings store.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

class WarningCategory(StrEnum):
    """Category of a pipeline warning shown to operators."""

    SOURCE_SKIPPED = "source_skipped"
    RECORD_SKIPPED = "record_skipped"
    PIPELINE_FAILED = "pipeline_failed"
    EARLY_WARNING_SEARCH_FAILED = "early_warning_search_failed"
    EARLY_WARNING_FETCH_FAILED = "early_warning_fetch_failed"
    EARLY_WARNING_RECORD_SKIPPED = "early_warning_record_skipped"
    EARLY_WARNING_PIPELINE_FAILED = "early_warning_pipeline_failed"

# All valid warning category string values.
WARNING_CATEGORIES: frozenset[str] = frozenset(WarningCategory)

# Soft cap on how many warnings are retained in storage.
MAX_WARNINGS_RETAINED = 200
# Maximum allowed length of a warning message body.
MAX_WARNING_MESSAGE_LENGTH = 4000

class PipelineWarning(BaseModel):
    """Persisted pipeline warning with acknowledgment state."""

    warning_id: str
    created_at: datetime
    category: WarningCategory
    message: str = Field(min_length=1, max_length=MAX_WARNING_MESSAGE_LENGTH)
    source: str | None = None
    acknowledged: bool = False
    run_id: str | None = None

class PipelineWarningCreate(BaseModel):
    """Payload used when creating a new pipeline warning."""

    category: WarningCategory
    message: str = Field(min_length=1, max_length=MAX_WARNING_MESSAGE_LENGTH)
    source: str | None = None
    run_id: str | None = None

class PipelineWarningsSummary(BaseModel):
    """Lightweight summary of unacknowledged pipeline warnings."""

    unacknowledged_count: int
