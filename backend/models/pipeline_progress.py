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
    EARLY_WARNING = "early_warning"
    EARLY_WARNING_SEARCH = "early_warning_search"
    EARLY_WARNING_FETCH = "early_warning_fetch"
    EARLY_WARNING_AGENT = "early_warning_agent"
    EARLY_WARNING_DB = "early_warning_db"

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
