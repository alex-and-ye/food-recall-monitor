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
from models.pipeline_run_status import PipelineProgressSnapshot
from services.pipeline_events import PipelineProgressBroadcaster

LOGGER = logging.getLogger(__name__)

FETCH_WEIGHT = 0.35
PROCESS_WEIGHT = 0.58
DB_WEIGHT = 0.07
AGENT_STEPS = ("translate_values", "summarize", "structure", "repair_and_convert")


class PipelineProgressTracker:
    def __init__(
        self,
        progress_broadcaster: PipelineProgressBroadcaster | None = None,
    ) -> None:
        self._lock = Lock()
        self._progress_broadcaster = progress_broadcaster
        self._run_status: dict[str, str] = {}
        self._run_started_monotonic: dict[str, float] = {}
        self._last_event_monotonic: dict[str, float] = {}
        self._stage_started_monotonic: dict[str, dict[str, float]] = {}
        self._run_log_paths: dict[str, str] = {}
        self._run_log_streams: dict[str, TextIO] = {}
        self._active_run_id: str | None = None
        self._snapshot = PipelineProgressSnapshot()
        self._run_options: dict[str, PipelineRunOptions] = {}
        self._sources_completed: dict[str, set[str]] = {}
        self._records_total: dict[str, int | None] = {}
        self._records_processed: dict[str, int] = {}
        self._current_record_index: dict[str, int] = {}
        self._current_record_step: dict[str, int] = {}
        self._estimated_records: dict[str, int] = {}

    def get_snapshot(self) -> PipelineProgressSnapshot:
        with self._lock:
            return self._snapshot.model_copy(deep=True)

    def is_running(self) -> bool:
        with self._lock:
            return self._snapshot.status == "running"

    def start_run(self, options: PipelineRunOptions) -> str:
        run_id = str(uuid4())
        now_monotonic = time.perf_counter()
        estimated_records = max(1, len(options.sources) * options.limit)
        with self._lock:
            self._run_status[run_id] = "running"
            self._run_started_monotonic[run_id] = now_monotonic
            self._last_event_monotonic[run_id] = now_monotonic
            self._stage_started_monotonic[run_id] = {}
            self._run_options[run_id] = options
            self._sources_completed[run_id] = set()
            self._records_total[run_id] = None
            self._records_processed[run_id] = 0
            self._current_record_index[run_id] = 0
            self._current_record_step[run_id] = 0
            self._estimated_records[run_id] = estimated_records
            self._active_run_id = run_id
            self._open_run_log_stream(run_id)
            self._snapshot = PipelineProgressSnapshot(
                run_id=run_id,
                status="running",
                percent=1.0,
                stage="pipeline",
                message="Pipeline run started",
                sources_total=len(options.sources),
                sources_completed=0,
                records_total=None,
                records_processed=0,
            )
            snapshot = self._snapshot.model_copy(deep=True)

        self._publish(snapshot)
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
            snapshot = self._update_progress_locked(
                run_id=run_id,
                stage=stage,
                message=message,
                source=source,
                details=event_details,
            )

        if snapshot is not None:
            self._publish(snapshot)

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
            self._snapshot = PipelineProgressSnapshot(
                run_id=run_id,
                status="completed",
                percent=100.0,
                stage="pipeline",
                message="Pipeline run completed",
                sources_total=self._snapshot.sources_total,
                sources_completed=self._snapshot.sources_total,
                records_total=records_fetched,
                records_processed=self._records_processed.get(run_id, 0),
                new_alerts_count=new_alerts_count,
            )
            snapshot = self._snapshot.model_copy(deep=True)

        self._publish(snapshot)
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
            self._run_status.pop(run_id, None)
            self._close_run_log_stream(run_id)
            if self._active_run_id == run_id:
                self._active_run_id = None
            # Keep the completed snapshot available for connected clients;
            # new connections can still read the terminal state until the
            # next run starts.

    def fail_run(self, *, run_id: str, error: str) -> None:
        with self._lock:
            if run_id not in self._run_status:
                return
            self._run_status[run_id] = "failed"
            self._snapshot = PipelineProgressSnapshot(
                run_id=run_id,
                status="failed",
                percent=self._snapshot.percent,
                stage="pipeline",
                message="Pipeline run failed",
                sources_total=self._snapshot.sources_total,
                sources_completed=self._snapshot.sources_completed,
                records_total=self._snapshot.records_total,
                records_processed=self._snapshot.records_processed,
                error=error,
            )
            snapshot = self._snapshot.model_copy(deep=True)

        self._publish(snapshot)
        self.append_event(
            run_id=run_id,
            stage="pipeline",
            message="Pipeline run failed",
            details={"error": error},
        )
        with self._lock:
            self._clear_timing_state(run_id)
            self._run_status.pop(run_id, None)
            self._close_run_log_stream(run_id)
            if self._active_run_id == run_id:
                self._active_run_id = None

    def _update_progress_locked(
        self,
        *,
        run_id: str,
        stage: str,
        message: str,
        source: str | None,
        details: dict[str, Any],
    ) -> PipelineProgressSnapshot | None:
        if self._run_status.get(run_id) not in {"running", "completed", "failed"}:
            return None

        options = self._run_options.get(run_id)
        sources_total = len(options.sources) if options is not None else self._snapshot.sources_total
        completed_sources = self._sources_completed.setdefault(run_id, set())

        if stage == "source" and _is_stage_end_message(message) and source:
            completed_sources.add(source)

        if stage == "fetch" and "records_fetched" in details:
            try:
                self._records_total[run_id] = int(details["records_fetched"])
            except (TypeError, ValueError):
                pass

        if stage == "record" and "record_index" in details:
            try:
                self._current_record_index[run_id] = int(details["record_index"])
            except (TypeError, ValueError):
                pass
            if message.strip().lower() in {
                "record processed successfully",
                "record processing failed",
            }:
                self._records_processed[run_id] = self._records_processed.get(run_id, 0) + 1
                self._current_record_step[run_id] = 0

        if stage == "agent":
            step_index = _agent_step_index(message)
            if step_index is not None:
                self._current_record_step[run_id] = step_index

        records_total = self._records_total.get(run_id)
        estimated_records = self._estimated_records.get(run_id, max(1, sources_total))
        effective_records = records_total if records_total is not None else estimated_records
        records_processed = self._records_processed.get(run_id, 0)
        current_record_index = self._current_record_index.get(run_id, 0)
        current_step = self._current_record_step.get(run_id, 0)

        fetch_progress = len(completed_sources) / max(1, sources_total)
        if stage in {"fetch", "source", "pipeline"} and records_total is None:
            # Nudge forward while crawling before sources finish.
            fetch_progress = min(0.95, fetch_progress + 0.05)

        if records_total == 0:
            process_progress = 1.0
        elif current_record_index > 0:
            record_fraction = (current_record_index - 1) / max(1, effective_records)
            step_fraction = current_step / max(1, len(AGENT_STEPS))
            process_progress = min(
                1.0,
                record_fraction + (step_fraction / max(1, effective_records)),
            )
            if records_processed > 0 and current_record_index <= records_processed:
                process_progress = max(
                    process_progress,
                    records_processed / max(1, effective_records),
                )
        else:
            process_progress = 0.0

        db_progress = 0.0
        if stage == "db" or message.strip().lower() == "pipeline run completed":
            db_progress = 1.0
        elif stage == "pipeline" and "completed" in message.lower():
            db_progress = 1.0

        percent = (
            fetch_progress * FETCH_WEIGHT
            + process_progress * PROCESS_WEIGHT
            + db_progress * DB_WEIGHT
        ) * 100.0

        if self._run_status.get(run_id) == "running":
            percent = min(99.0, max(1.0, percent))
        elif self._run_status.get(run_id) == "completed":
            percent = 100.0

        status_value = self._run_status.get(run_id, "running")
        mapped_status = (
            "running"
            if status_value == "running"
            else "completed"
            if status_value == "completed"
            else "failed"
        )

        self._snapshot = PipelineProgressSnapshot(
            run_id=run_id,
            status=mapped_status,
            percent=round(percent, 1),
            stage=stage,
            message=message,
            sources_total=sources_total,
            sources_completed=len(completed_sources),
            records_total=records_total,
            records_processed=records_processed,
            new_alerts_count=self._snapshot.new_alerts_count,
            error=self._snapshot.error,
        )
        return self._snapshot.model_copy(deep=True)

    def _publish(self, snapshot: PipelineProgressSnapshot) -> None:
        if self._progress_broadcaster is not None:
            self._progress_broadcaster.notify(snapshot)

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
        self._run_options.pop(run_id, None)
        self._sources_completed.pop(run_id, None)
        self._records_total.pop(run_id, None)
        self._records_processed.pop(run_id, None)
        self._current_record_index.pop(run_id, None)
        self._current_record_step.pop(run_id, None)
        self._estimated_records.pop(run_id, None)

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


def _agent_step_index(message: str) -> int | None:
    normalized = message.strip().lower()
    for index, step_name in enumerate(AGENT_STEPS, start=1):
        if normalized.startswith(step_name):
            return index
    return None


def _stage_key(*, stage: str, source: str | None) -> str:
    return f"{stage}::{source or '*'}"


def _display_timestamp(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return value
    return parsed.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
