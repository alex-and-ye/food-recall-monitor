"""Abstract persistence contract for pipeline run log events.

Defines the repository interface for appending and querying structured
log events produced by recall and early-warning pipeline runs.
"""

from abc import ABC, abstractmethod

from models.pipeline_run_log import PipelineKind, PipelineRunLogEvent

class PipelineRunLogsDBInterface(ABC):
    """Repository interface for pipeline run log event persistence."""

    @abstractmethod
    def append(self, event: PipelineRunLogEvent) -> PipelineRunLogEvent:
        """Persist a pipeline run log event (insert or replace by event ID).

        Args:
            event: Log event to store.

        Returns:
            The stored event.
        """
        pass

    @abstractmethod
    def list_events(
        self,
        *,
        run_id: str | None = None,
        pipeline_kind: PipelineKind | None = None,
        limit: int | None = None,
    ) -> list[PipelineRunLogEvent]:
        """List log events with optional filters.

        Args:
            run_id: If set, only events for this run.
            pipeline_kind: If set, only events for this pipeline kind.
            limit: Maximum number of events to return; None for no limit.

        Returns:
            Matching events, newest first.

        Raises:
            ValueError: If limit is negative.
        """
        pass

    @abstractmethod
    def list_run_ids(
        self,
        *,
        pipeline_kind: PipelineKind | None = None,
        limit: int | None = None,
    ) -> list[str]:
        """List distinct run IDs ordered by most recent activity.

        Args:
            pipeline_kind: If set, only runs of this pipeline kind.
            limit: Maximum number of run IDs to return; None for no limit.

        Returns:
            Distinct run IDs, most recently active first.
        """
        pass

    @abstractmethod
    def count_events(self) -> int:
        """Return the total number of stored log events.

        Returns:
            Count of events in the store.
        """
        pass
