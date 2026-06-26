from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

ProgressStatus = Literal["running", "completed", "failed"]


class ProgressReporter(Protocol):
    def log(
        self,
        *,
        stage: str,
        message: str,
        source: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        ...


class PipelineProgressEvent(BaseModel):
    timestamp: str
    stage: str
    message: str
    source: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class PipelineRunProgress(BaseModel):
    run_id: str
    status: ProgressStatus
    started_at: str
    finished_at: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)
    events: list[PipelineProgressEvent] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
