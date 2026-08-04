"""Pipeline run log event models for durable progress history.

Stores per-event status lines for official and early-warning runs,
including Chroma document/metadata conversion.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator

class PipelineKind(StrEnum):
    """Which pipeline produced a run-log event."""

    OFFICIAL = "official"
    EARLY_WARNING = "early_warning"

class PipelineRunLogEvent(BaseModel):
    """A single durable progress/status event within a pipeline run."""

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
        """Attach UTC when ``created_at`` lacks timezone info."""
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    def to_document(self) -> str:
        """Serialize the event to a compact JSON document string."""
        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            default=str,
        )

    def to_metadata(self) -> dict[str, str | int | float | bool]:
        """Flatten the event into Chroma-compatible scalar metadata."""
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
        """Deserialize a run-log event from a JSON document string.

        Args:
            document: JSON object string for the event.

        Returns:
            Validated ``PipelineRunLogEvent``.

        Raises:
            ValueError: If the payload is not a JSON object.
        """
        payload = json.loads(document)
        if not isinstance(payload, dict):
            raise ValueError("pipeline run log document must contain an object")
        return cls.model_validate(payload)

# Soft cap on how many run-log events are retained in storage.
MAX_PIPELINE_LOG_EVENTS_RETAINED = 5000
