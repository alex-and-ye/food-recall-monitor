import json
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator

class PipelineKind(StrEnum):
    OFFICIAL = "official"
    EARLY_WARNING = "early_warning"

class PipelineRunLogEvent(BaseModel):
    event_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    pipeline_kind: PipelineKind
    created_at: datetime
    status: str = "running"
    stage: str
    message: str = Field(min_length=1)
    source: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)

    @field_validator("created_at")
    @classmethod
    def _ensure_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    def to_document(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            default=str,
        )

    def to_metadata(self) -> dict[str, str | int | float | bool]:
        metadata: dict[str, str | int | float | bool] = {
            "event_id": self.event_id,
            "run_id": self.run_id,
            "pipeline_kind": self.pipeline_kind.value,
            "created_at": self.created_at.isoformat(),
            "status": self.status,
            "stage": self.stage,
            "message": self.message[:280],
        }
        if self.source:
            metadata["source"] = self.source
        return metadata

    @classmethod
    def from_document(cls, document: str) -> PipelineRunLogEvent:
        payload = json.loads(document)
        if not isinstance(payload, dict):
            raise ValueError("pipeline run log document must contain an object")
        return cls.model_validate(payload)

MAX_PIPELINE_LOG_EVENTS_RETAINED = 5000
