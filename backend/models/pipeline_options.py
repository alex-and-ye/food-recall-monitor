from enum import Enum

from pydantic import BaseModel, Field


class RecallSource(str, Enum):
    FRANCE = "france"
    UK = "uk"
    US = "us"


class PipelineRunOptions(BaseModel):
    sources: list[RecallSource] = Field(
        default_factory=lambda: [
            RecallSource.FRANCE,
            RecallSource.UK,
            RecallSource.US,
        ]
    )
    limit: int = Field(default=10, ge=1, le=100)
