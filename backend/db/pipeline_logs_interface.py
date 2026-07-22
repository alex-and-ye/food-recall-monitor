from __future__ import annotations

from abc import ABC, abstractmethod

from models.pipeline_run_log import PipelineKind, PipelineRunLogEvent


class PipelineRunLogsDBInterface(ABC):
    @abstractmethod
    def append(self, event: PipelineRunLogEvent) -> PipelineRunLogEvent:
        pass

    @abstractmethod
    def list_events(
        self,
        *,
        run_id: str | None = None,
        pipeline_kind: PipelineKind | None = None,
        limit: int | None = None,
    ) -> list[PipelineRunLogEvent]:
        pass

    @abstractmethod
    def list_run_ids(
        self,
        *,
        pipeline_kind: PipelineKind | None = None,
        limit: int | None = None,
    ) -> list[str]:
        pass

    @abstractmethod
    def count_events(self) -> int:
        pass
