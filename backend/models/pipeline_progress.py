"""Pipeline progress stage labels and reporter protocol.

Defines stage identifiers used in progress events and the structural
typing contract for progress reporters.
"""

from enum import StrEnum
from typing import Any, Protocol

class PipelineStage(StrEnum):
    """Named stages emitted in pipeline progress / log events."""

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
    """Protocol for objects that accept structured pipeline progress logs."""

    def log(
        self,
        *,
        stage: str,
        message: str,
        source: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Record a progress event for a pipeline stage.

        Args:
            stage: Stage label (typically a ``PipelineStage`` value).
            message: Human-readable progress message.
            source: Optional source name related to the event.
            details: Optional structured detail payload.
        """
        ...
