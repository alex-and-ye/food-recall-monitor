from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from threading import Lock
from uuid import uuid4

from models.pipeline_options import PipelineRunOptions
from models.pipeline_progress import PipelineProgressEvent, PipelineRunProgress

MAX_EVENTS_PER_RUN = 1_000
MAX_RUNS_STORED = 50


class PipelineProgressTracker:
    def __init__(self) -> None:
        self._lock = Lock()
        self._runs: dict[str, PipelineRunProgress] = {}
        self._run_order: list[str] = []

    def start_run(self, options: PipelineRunOptions) -> str:
        run_id = str(uuid4())
        started_at = _iso_now()
        run = PipelineRunProgress(
            run_id=run_id,
            status="running",
            started_at=started_at,
            options=options.model_dump(),
        )
        with self._lock:
            self._runs[run_id] = run
            self._run_order.insert(0, run_id)
            self._trim_old_runs()
        self.append_event(
            run_id=run_id,
            stage="pipeline",
            message="Pipeline run started",
            details={"options": options.model_dump()},
        )
        return run_id

    def reporter(self, run_id: str) -> _TrackerReporter:
        return _TrackerReporter(tracker=self, run_id=run_id)

    def append_event(
        self,
        *,
        run_id: str,
        stage: str,
        message: str,
        source: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        event = PipelineProgressEvent(
            timestamp=_iso_now(),
            stage=stage,
            message=message,
            source=source,
            details=details or {},
        )
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return
            run.events.append(event)
            if len(run.events) > MAX_EVENTS_PER_RUN:
                run.events = run.events[-MAX_EVENTS_PER_RUN:]

    def complete_run(
        self,
        *,
        run_id: str,
        new_alerts_count: int,
        records_fetched: int,
        source_failures: dict[str, str],
    ) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return
            run.status = "completed"
            run.finished_at = _iso_now()
            run.summary = {
                "new_alerts_count": new_alerts_count,
                "records_fetched": records_fetched,
                "source_failures": source_failures,
            }
        self.append_event(
            run_id=run_id,
            stage="pipeline",
            message="Pipeline run completed",
            details={
                "new_alerts_count": new_alerts_count,
                "records_fetched": records_fetched,
                "source_failures": source_failures,
            },
        )

    def fail_run(self, *, run_id: str, error: str) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return
            run.status = "failed"
            run.finished_at = _iso_now()
            run.summary = {"error": error}
        self.append_event(
            run_id=run_id,
            stage="pipeline",
            message="Pipeline run failed",
            details={"error": error},
        )

    def get_run(self, run_id: str) -> PipelineRunProgress | None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return None
            return deepcopy(run)

    def list_runs(self, *, limit: int = 10) -> list[PipelineRunProgress]:
        with self._lock:
            run_ids = self._run_order[: max(1, limit)]
            runs = [self._runs[run_id] for run_id in run_ids if run_id in self._runs]
            return deepcopy(runs)

    def _trim_old_runs(self) -> None:
        if len(self._run_order) <= MAX_RUNS_STORED:
            return
        stale_run_ids = self._run_order[MAX_RUNS_STORED:]
        self._run_order = self._run_order[:MAX_RUNS_STORED]
        for run_id in stale_run_ids:
            self._runs.pop(run_id, None)


class _TrackerReporter:
    def __init__(self, *, tracker: PipelineProgressTracker, run_id: str) -> None:
        self._tracker = tracker
        self.run_id = run_id

    def log(
        self,
        *,
        stage: str,
        message: str,
        source: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        self._tracker.append_event(
            run_id=self.run_id,
            stage=stage,
            message=message,
            source=source,
            details=details,
        )


def _iso_now() -> str:
    return datetime.now(tz=UTC).isoformat()
