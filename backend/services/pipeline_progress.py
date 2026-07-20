from __future__ import annotations

from datetime import UTC, datetime
import json
import logging
from threading import Lock
import time
from typing import Any, TextIO
from uuid import uuid4

from paths import get_run_logs_dir
from models.pipeline_options import PipelineRunOptions
from models.pipeline_progress import PipelineStage

LOGGER = logging.getLogger(__name__)


class PipelineProgressTracker:
    def __init__(self) -> None:
        self._lock = Lock()
        self._run_status: dict[str, str] = {}
        self._run_started_monotonic: dict[str, float] = {}
        self._last_event_monotonic: dict[str, float] = {}
        self._stage_started_monotonic: dict[str, dict[str, float]] = {}
        self._run_log_paths: dict[str, str] = {}
        self._run_log_streams: dict[str, TextIO] = {}

    def start_run(self, options: PipelineRunOptions) -> str:
        run_id = str(uuid4())
        now_monotonic = time.perf_counter()
        with self._lock:
            self._run_status[run_id] = "running"
            self._run_started_monotonic[run_id] = now_monotonic
            self._last_event_monotonic[run_id] = now_monotonic
            self._stage_started_monotonic[run_id] = {}
            self._open_run_log_stream(run_id)
        self.append_event(
            run_id=run_id,
            stage=PipelineStage.PIPELINE,
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

            self._write_run_log_event(
                run_id=run_id,
                status=self._run_status[run_id],
                timestamp=_iso_now(),
                stage=stage,
                message=message,
                source=source,
                details=event_details,
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
            if run_id not in self._run_status:
                return
            self._run_status[run_id] = "completed"
        self.append_event(
            run_id=run_id,
            stage=PipelineStage.PIPELINE,
            message="Pipeline run completed",
            details={
                "new_alerts_count": new_alerts_count,
                "records_fetched": records_fetched,
                "source_failures": source_failures,
            },
        )
        with self._lock:
            self._clear_timing_state(run_id)
            self._run_status.pop(run_id, None)
            self._close_run_log_stream(run_id)

    def fail_run(self, *, run_id: str, error: str) -> None:
        with self._lock:
            if run_id not in self._run_status:
                return
            self._run_status[run_id] = "failed"
        self.append_event(
            run_id=run_id,
            stage=PipelineStage.PIPELINE,
            message="Pipeline run failed",
            details={"error": error},
        )
        with self._lock:
            self._clear_timing_state(run_id)
            self._run_status.pop(run_id, None)
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
        timestamp: str,
        stage: str,
        message: str,
        source: str | None,
        details: dict[str, Any],
    ) -> None:
        stream = self._run_log_streams.get(run_id)
        if stream is None:
            return

        source_label = source or "-"
        level = "ERROR" if status.upper() == "FAILED" else "INFO"
        line = (
            f"{_display_timestamp(timestamp)} | {level:<8} | pipeline.run.{run_id[:8]} "
            f"| stage={stage:<10} source={source_label:<20} status={status.upper():<9} | {message}"
        )
        stream.write(f"{line}\n")
        if details:
            stream.write("  details:\n")
            detail_json = json.dumps(details, ensure_ascii=False, indent=2, default=str)
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
