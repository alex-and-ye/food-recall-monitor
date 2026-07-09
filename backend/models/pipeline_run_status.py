from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

PipelineRunStatusValue = Literal["idle", "running", "completed", "failed"]


class PipelineProgressSnapshot(BaseModel):
    run_id: str | None = None
    status: PipelineRunStatusValue = "idle"
    percent: float = Field(default=0.0, ge=0.0, le=100.0)
    stage: str = "idle"
    message: str = "Ready"
    sources_total: int = 0
    sources_completed: int = 0
    records_total: int | None = None
    records_processed: int = 0
    new_alerts_count: int | None = None
    error: str | None = None


class PipelineRunStartResponse(BaseModel):
    run_id: str
    status: Literal["started", "already_running"]
    message: str
