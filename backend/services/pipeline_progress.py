from __future__ import annotations

from datetime import UTC, datetime
import logging
from threading import Lock
import time
from uuid import uuid4

from db.pipeline_logs_interface import PipelineRunLogsDBInterface
from models.pipeline_options import PipelineRunOptions
from models.pipeline_progress import PipelineStage
from models.pipeline_run_log import PipelineKind, PipelineRunLogEvent

LOGGER = logging.getLogger(__name__)

class PipelineProgressTracker:
    def __init__(self, log_store: PipelineRunLogsDBInterface) -> None:
        self._log_store = log_store
        self._lock = Lock()
        self._run_status: dict[str, str] = {}
        self._run_kinds: dict[str, PipelineKind] = {}
        self._run_started_monotonic: dict[str, float] = {}
        self._last_event_monotonic: dict[str, float] = {}
        self._stage_started_monotonic: dict[str, dict[str, float]] = {}

    def start_run(
        self,
        options: PipelineRunOptions | None = None,
        *,
        pipeline_kind: PipelineKind | str = PipelineKind.OFFICIAL,
        details: dict[str, object] | None = None,
    ) -> str:
        run_id = str(uuid4())
        kind = PipelineKind(pipeline_kind)
        now_monotonic = time.perf_counter()
        with self._lock:
            self._run_status[run_id] = "running"
            self._run_kinds[run_id] = kind
            self._run_started_monotonic[run_id] = now_monotonic
            self._last_event_monotonic[run_id] = now_monotonic
            self._stage_started_monotonic[run_id] = {}

        start_details = dict(details or {})
        if options is not None:
            start_details["options"] = options.model_dump()
        self.append_event(
            run_id=run_id,
            stage=(
                PipelineStage.PIPELINE
                if kind == PipelineKind.OFFICIAL
                else PipelineStage.EARLY_WARNING
            ),
            message=(
                "Pipeline run started"
                if kind == PipelineKind.OFFICIAL
                else "Early-warning pipeline run started"
            ),
            details=start_details,
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
        with self._lock:
            if run_id not in self._run_status:
                return

            now_monotonic = time.perf_counter()
            event_details = dict(details or {})
            timing_details = self._derive_timing_details(
                run_id=run_id,
                stage=stage,
                source=source,
                message=message,
                now_monotonic=now_monotonic,
            )
            event_details.update(timing_details)
            status = self._run_status[run_id]
            pipeline_kind = self._run_kinds[run_id]
            event = PipelineRunLogEvent(
                event_id=str(uuid4()),
                run_id=run_id,
                pipeline_kind=pipeline_kind,
                created_at=datetime.now(tz=UTC),
                status=status,
                stage=str(stage),
                message=message,
                source=source,
                details=event_details,
            )

        try:
            self._log_store.append(event)
        except Exception:
            LOGGER.exception(
                "Failed to persist pipeline run log event",
                extra={"run_id": run_id, "stage": stage},
            )

    def complete_run(
        self,
        *,
        run_id: str,
        new_alerts_count: int | None = None,
        records_fetched: int | None = None,
        source_failures: dict[str, str] | None = None,
        summary: dict[str, object] | None = None,
    ) -> None:
        with self._lock:
            if run_id not in self._run_status:
                return
            self._run_status[run_id] = "completed"
            pipeline_kind = self._run_kinds.get(run_id, PipelineKind.OFFICIAL)

        details = dict(summary or {})
        if new_alerts_count is not None:
            details["new_alerts_count"] = new_alerts_count
        if records_fetched is not None:
            details["records_fetched"] = records_fetched
        if source_failures is not None:
            details["source_failures"] = source_failures

        self.append_event(
            run_id=run_id,
            stage=(
                PipelineStage.PIPELINE
                if pipeline_kind == PipelineKind.OFFICIAL
                else PipelineStage.EARLY_WARNING
            ),
            message=(
                "Pipeline run completed"
                if pipeline_kind == PipelineKind.OFFICIAL
                else "Early-warning pipeline run completed"
            ),
            details=details,
        )
        with self._lock:
            self._clear_timing_state(run_id)
            self._run_status.pop(run_id, None)
            self._run_kinds.pop(run_id, None)

    def fail_run(self, *, run_id: str, error: str) -> None:
        with self._lock:
            if run_id not in self._run_status:
                return
            self._run_status[run_id] = "failed"
            pipeline_kind = self._run_kinds.get(run_id, PipelineKind.OFFICIAL)

        self.append_event(
            run_id=run_id,
            stage=(
                PipelineStage.PIPELINE
                if pipeline_kind == PipelineKind.OFFICIAL
                else PipelineStage.EARLY_WARNING
            ),
            message=(
                "Pipeline run failed"
                if pipeline_kind == PipelineKind.OFFICIAL
                else "Early-warning pipeline run failed"
            ),
            details={"error": error},
        )
        with self._lock:
            self._clear_timing_state(run_id)
            self._run_status.pop(run_id, None)
            self._run_kinds.pop(run_id, None)

    def _derive_timing_details(
        self,
        *,
        run_id: str,
        stage: str,
        source: str | None,
        message: str,
        now_monotonic: float,
    ) -> dict[str, float]:
        timing_details: dict[str, float] = {}

        run_started = self._run_started_monotonic.get(run_id)
        if run_started is not None:
            timing_details["run_elapsed_seconds"] = round(now_monotonic - run_started, 3)

        previous_event = self._last_event_monotonic.get(run_id)
        if previous_event is not None:
            timing_details["since_previous_event_seconds"] = round(
                now_monotonic - previous_event, 3
            )
        self._last_event_monotonic[run_id] = now_monotonic

        stage_key = _stage_key(stage=stage, source=source)
        stage_timings = self._stage_started_monotonic.setdefault(run_id, {})
        if _is_stage_start_message(message):
            stage_timings[stage_key] = now_monotonic
        if _is_stage_end_message(message):
            stage_started = stage_timings.pop(stage_key, None)
            if stage_started is not None:
                timing_details["stage_duration_seconds"] = round(
                    now_monotonic - stage_started, 3
                )

        return timing_details

    def _clear_timing_state(self, run_id: str) -> None:
        self._run_started_monotonic.pop(run_id, None)
        self._last_event_monotonic.pop(run_id, None)
        self._stage_started_monotonic.pop(run_id, None)

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

def _is_stage_start_message(message: str) -> bool:
    normalized = message.strip().lower()
    return normalized.startswith("starting ") or normalized.endswith(" started")

def _is_stage_end_message(message: str) -> bool:
    normalized = message.strip().lower()
    terminal_markers = (
        "completed",
        "finished",
        "failed",
        "processed successfully",
        "processing failed",
    )
    return any(marker in normalized for marker in terminal_markers)

def _stage_key(*, stage: str, source: str | None) -> str:
    return f"{stage}::{source or '*'}"
