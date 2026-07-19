from __future__ import annotations

from enum import StrEnum
from typing import Any, Protocol

class PipelineStage(StrEnum):
    PIPELINE = "pipeline"
    FETCH = "fetch"
    RECORD = "record"
    AGENT = "agent"
    DISCOVERY = "discovery"
    SOURCE = "source"
    CRAWL = "crawl"
    DB = "db"

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
