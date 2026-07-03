from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import json
import logging
from threading import Lock
import time
from typing import TextIO
from uuid import uuid4

from paths import get_run_logs_dir
from models.pipeline_options import PipelineRunOptions
from models.pipeline_progress import PipelineProgressEvent, PipelineRunProgress

MAX_EVENTS_PER_RUN = 1_000
MAX_RUNS_STORED = 50
LOGGER = logging.getLogger(__name__)


class PipelineProgressTracker:
    def __init__(self) -> None:
        self._lock = Lock()
        self._runs: dict[str, PipelineRunProgress] = {}
        self._run_order: list[str] = []
        self._run_started_monotonic: dict[str, float] = {}
        self._last_event_monotonic: dict[str, float] = {}
        self._stage_started_monotonic: dict[str, dict[str, float]] = {}
        self._run_log_paths: dict[str, str] = {}
        self._run_log_streams: dict[str, TextIO] = {}

    def start_run(self, options: PipelineRunOptions) -> str:
        run_id = str(uuid4())
        started_at = _iso_now()
        now_monotonic = time.perf_counter()
        run = PipelineRunProgress(
            run_id=run_id,
            status="running",
            started_at=started_at,
            options=options.model_dump(),
        )
        with self._lock:
            self._runs[run_id] = run
            self._run_order.insert(0, run_id)
            self._run_started_monotonic[run_id] = now_monotonic
            self._last_event_monotonic[run_id] = now_monotonic
            self._stage_started_monotonic[run_id] = {}
            self._open_run_log_stream(run_id)
            self._trim_old_runs()
        self.append_event(
            run_id=run_id,
            stage="pipeline",
            message="Pipeline run started",
            details={
                "options": options.model_dump(),
                "run_log_file": self._run_log_paths.get(run_id),
            },
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
        run_status: str | None = None
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
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

            event = PipelineProgressEvent(
                timestamp=_iso_now(),
                stage=stage,
                message=message,
                source=source,
                details=event_details,
            )
            run.events.append(event)
            if len(run.events) > MAX_EVENTS_PER_RUN:
                run.events = run.events[-MAX_EVENTS_PER_RUN:]
            run_status = run.status

        with self._lock:
            self._write_run_log_event(
                run_id=run_id,
                status=run_status or "unknown",
                event=event,
            )

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
        with self._lock:
            self._clear_timing_state(run_id)
            self._close_run_log_stream(run_id)

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
        with self._lock:
            self._clear_timing_state(run_id)
            self._close_run_log_stream(run_id)

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
            self._clear_timing_state(run_id)
            self._close_run_log_stream(run_id)

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
            timing_details["since_previous_event_seconds"] = round(now_monotonic - previous_event, 3)
        self._last_event_monotonic[run_id] = now_monotonic

        stage_key = _stage_key(stage=stage, source=source)
        stage_timings = self._stage_started_monotonic.setdefault(run_id, {})
        if _is_stage_start_message(message):
            stage_timings[stage_key] = now_monotonic
        if _is_stage_end_message(message):
            stage_started = stage_timings.pop(stage_key, None)
            if stage_started is not None:
                timing_details["stage_duration_seconds"] = round(now_monotonic - stage_started, 3)

        return timing_details

    def _clear_timing_state(self, run_id: str) -> None:
        self._run_started_monotonic.pop(run_id, None)
        self._last_event_monotonic.pop(run_id, None)
        self._stage_started_monotonic.pop(run_id, None)

    def _open_run_log_stream(self, run_id: str) -> None:
        timestamp = datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")
        file_name = f"pipeline_run_{timestamp}_{run_id[:8]}.log"
        path = get_run_logs_dir() / file_name
        try:
            stream = path.open("a", encoding="utf-8")
        except OSError:
            LOGGER.exception("Failed to open run log file", extra={"run_id": run_id, "log_file": path})
            return

        self._run_log_paths[run_id] = str(path)
        self._run_log_streams[run_id] = stream
        stream.write(f"=== Pipeline Run {run_id} ===\n")
        stream.write(f"Started: {_iso_now()}\n")
        stream.write(f"Log file: {path}\n\n")
        stream.flush()

    def _close_run_log_stream(self, run_id: str) -> None:
        stream = self._run_log_streams.pop(run_id, None)
        self._run_log_paths.pop(run_id, None)
        if stream is None:
            return
        try:
            stream.write(f"\nFinished: {_iso_now()}\n")
            stream.close()
        except OSError:
            LOGGER.exception("Failed to close run log file", extra={"run_id": run_id})

    def _write_run_log_event(
        self,
        *,
        run_id: str,
        status: str,
        event: PipelineProgressEvent,
    ) -> None:
        stream = self._run_log_streams.get(run_id)
        if stream is None:
            return

        source = event.source or "-"
        level = "ERROR" if status.upper() == "FAILED" else "INFO"
        line = (
            f"{_display_timestamp(event.timestamp)} | {level:<8} | pipeline.run.{run_id[:8]} "
            f"| stage={event.stage:<10} source={source:<20} status={status.upper():<9} | {event.message}"
        )
        stream.write(f"{line}\n")
        if event.details:
            stream.write("  details:\n")
            detail_json = json.dumps(event.details, ensure_ascii=False, indent=2, default=str)
            for detail_line in detail_json.splitlines():
                stream.write(f"    {detail_line}\n")
        stream.write("\n")
        stream.flush()


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


def _display_timestamp(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return value
    return parsed.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
