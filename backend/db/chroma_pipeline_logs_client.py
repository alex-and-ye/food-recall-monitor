"""ChromaDB and in-memory stores for pipeline run log events.

Persists structured pipeline log events with retention pruning, plus an
in-memory test double that mirrors the same append/list/prune behavior.
"""

from typing import cast

import chromadb
from chromadb.api.types import Metadata

from db.pipeline_logs_interface import PipelineRunLogsDBInterface
from models.pipeline_run_log import (
    MAX_PIPELINE_LOG_EVENTS_RETAINED,
    PipelineKind,
    PipelineRunLogEvent,
)

class PipelineRunLogsChromaClient(PipelineRunLogsDBInterface):
    """Chroma-backed store for pipeline run log events."""

    # Chroma collection name for pipeline run log events
    COLLECTION_NAME = "pipeline_run_logs_collection"

    def __init__(self, host: str, port: int) -> None:
        """Connect to Chroma and ensure the pipeline logs collection exists.

        Args:
            host: Chroma HTTP host.
            port: Chroma HTTP port.
        """
        self.client = chromadb.HttpClient(host=host, port=port)
        self.collection = self.client.get_or_create_collection(name=self.COLLECTION_NAME)

    def append(self, event: PipelineRunLogEvent) -> PipelineRunLogEvent:
        """Upsert a log event and prune oldest records past the retention cap.

        Args:
            event: Log event to store.

        Returns:
            The same event after upsert.
        """
        self.collection.upsert(
            ids=[event.event_id],
            documents=[event.to_document()],
            metadatas=[cast(Metadata, event.to_metadata())],
        )
        self._prune_oldest()
        return event

    def list_events(
        self,
        *,
        run_id: str | None = None,
        pipeline_kind: PipelineKind | None = None,
        limit: int | None = None,
    ) -> list[PipelineRunLogEvent]:
        """List log events with optional filters, newest first.

        Args:
            run_id: If set, only events for this run.
            pipeline_kind: If set, only events for this pipeline kind.
            limit: Max events to return; None for unlimited.

        Returns:
            Matching events sorted by created_at descending.

        Raises:
            ValueError: If limit is negative.
        """
        events = self._all_events()
        if run_id is not None:
            events = [event for event in events if event.run_id == run_id]
        if pipeline_kind is not None:
            events = [event for event in events if event.pipeline_kind == pipeline_kind]
        events.sort(key=lambda item: (item.created_at, item.event_id), reverse=True)
        if limit is not None:
            if limit < 0:
                raise ValueError("limit must be non-negative")
            events = events[:limit]
        return events

    def list_run_ids(
        self,
        *,
        pipeline_kind: PipelineKind | None = None,
        limit: int | None = None,
    ) -> list[str]:
        """List distinct run IDs ordered by most recent event activity.

        Args:
            pipeline_kind: If set, only runs of this pipeline kind.
            limit: Max run IDs to return; None for unlimited.

        Returns:
            Distinct run IDs, most recently active first.
        """
        events = self.list_events(pipeline_kind=pipeline_kind)
        run_ids: list[str] = []
        seen: set[str] = set()
        for event in events:
            if event.run_id in seen:
                continue
            seen.add(event.run_id)
            run_ids.append(event.run_id)
            if limit is not None and len(run_ids) >= limit:
                break
        return run_ids

    def count_events(self) -> int:
        """Return the number of log event documents in the collection.

        Returns:
            Total event count.
        """
        results = self.collection.get(include=[])
        return len(results.get("ids") or [])

    def _all_events(self) -> list[PipelineRunLogEvent]:
        """Load and parse all events from Chroma documents.

        Returns:
            Successfully parsed events (invalid documents are skipped).
        """
        results = self.collection.get(include=["documents"])
        events: list[PipelineRunLogEvent] = []
        for document in results.get("documents") or []:
            if not document:
                continue
            try:
                events.append(PipelineRunLogEvent.from_document(document))
            except (TypeError, ValueError):
                continue
        return events

    def _prune_oldest(self) -> None:
        """Delete oldest events when count exceeds MAX_PIPELINE_LOG_EVENTS_RETAINED."""
        events = self._all_events()
        if len(events) <= MAX_PIPELINE_LOG_EVENTS_RETAINED:
            return
        events.sort(key=lambda item: (item.created_at, item.event_id))
        overflow = len(events) - MAX_PIPELINE_LOG_EVENTS_RETAINED
        stale_ids = [event.event_id for event in events[:overflow]]
        if stale_ids:
            self.collection.delete(ids=stale_ids)

class InMemoryPipelineRunLogsStore(PipelineRunLogsDBInterface):
    """In-memory test double for pipeline run log persistence."""

    def __init__(self) -> None:
        """Initialize an empty in-memory event map."""
        self._events: dict[str, PipelineRunLogEvent] = {}

    def append(self, event: PipelineRunLogEvent) -> PipelineRunLogEvent:
        """Store a deep copy of the event and prune if over retention.

        Args:
            event: Log event to store.

        Returns:
            Deep copy of the stored event.
        """
        stored = event.model_copy(deep=True)
        self._events[stored.event_id] = stored
        self._prune_oldest()
        return stored.model_copy(deep=True)

    def list_events(
        self,
        *,
        run_id: str | None = None,
        pipeline_kind: PipelineKind | None = None,
        limit: int | None = None,
    ) -> list[PipelineRunLogEvent]:
        """List deep-copied events with optional filters, newest first.

        Args:
            run_id: If set, only events for this run.
            pipeline_kind: If set, only events for this pipeline kind.
            limit: Max events to return; None for unlimited.

        Returns:
            Matching deep-copied events.

        Raises:
            ValueError: If limit is negative.
        """
        events = [event.model_copy(deep=True) for event in self._events.values()]
        if run_id is not None:
            events = [event for event in events if event.run_id == run_id]
        if pipeline_kind is not None:
            events = [event for event in events if event.pipeline_kind == pipeline_kind]
        events.sort(key=lambda item: (item.created_at, item.event_id), reverse=True)
        if limit is not None:
            if limit < 0:
                raise ValueError("limit must be non-negative")
            events = events[:limit]
        return events

    def list_run_ids(
        self,
        *,
        pipeline_kind: PipelineKind | None = None,
        limit: int | None = None,
    ) -> list[str]:
        """List distinct run IDs ordered by most recent event activity.

        Args:
            pipeline_kind: If set, only runs of this pipeline kind.
            limit: Max run IDs to return; None for unlimited.

        Returns:
            Distinct run IDs, most recently active first.
        """
        events = self.list_events(pipeline_kind=pipeline_kind)
        run_ids: list[str] = []
        seen: set[str] = set()
        for event in events:
            if event.run_id in seen:
                continue
            seen.add(event.run_id)
            run_ids.append(event.run_id)
            if limit is not None and len(run_ids) >= limit:
                break
        return run_ids

    def count_events(self) -> int:
        """Return the number of events in memory.

        Returns:
            Total event count.
        """
        return len(self._events)

    def _prune_oldest(self) -> None:
        """Remove oldest events when count exceeds the retention cap."""
        if len(self._events) <= MAX_PIPELINE_LOG_EVENTS_RETAINED:
            return
        ordered = sorted(
            self._events.values(),
            key=lambda item: (item.created_at, item.event_id),
        )
        overflow = len(ordered) - MAX_PIPELINE_LOG_EVENTS_RETAINED
        for event in ordered[:overflow]:
            self._events.pop(event.event_id, None)
