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
    COLLECTION_NAME = "pipeline_run_logs_collection"

    def __init__(self, host: str, port: int) -> None:
        self.client = chromadb.HttpClient(host=host, port=port)
        self.collection = self.client.get_or_create_collection(name=self.COLLECTION_NAME)

    def append(self, event: PipelineRunLogEvent) -> PipelineRunLogEvent:
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
        results = self.collection.get(include=[])
        return len(results.get("ids") or [])

    def _all_events(self) -> list[PipelineRunLogEvent]:
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
        events = self._all_events()
        if len(events) <= MAX_PIPELINE_LOG_EVENTS_RETAINED:
            return
        events.sort(key=lambda item: (item.created_at, item.event_id))
        overflow = len(events) - MAX_PIPELINE_LOG_EVENTS_RETAINED
        stale_ids = [event.event_id for event in events[:overflow]]
        if stale_ids:
            self.collection.delete(ids=stale_ids)

class InMemoryPipelineRunLogsStore(PipelineRunLogsDBInterface):
    def __init__(self) -> None:
        self._events: dict[str, PipelineRunLogEvent] = {}

    def append(self, event: PipelineRunLogEvent) -> PipelineRunLogEvent:
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
        return len(self._events)

    def _prune_oldest(self) -> None:
        if len(self._events) <= MAX_PIPELINE_LOG_EVENTS_RETAINED:
            return
        ordered = sorted(
            self._events.values(),
            key=lambda item: (item.created_at, item.event_id),
        )
        overflow = len(ordered) - MAX_PIPELINE_LOG_EVENTS_RETAINED
        for event in ordered[:overflow]:
            self._events.pop(event.event_id, None)
