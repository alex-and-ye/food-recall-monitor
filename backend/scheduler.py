"""Background schedulers for daily official and early-warning pipeline runs.

Computes delay until the configured daily run time, sleeps until then (or
until stopped), then invokes the corresponding pipeline wrapper.
"""

import asyncio
import logging
from datetime import datetime, time, timedelta

from pipeline_runner import run_early_warning_wrapper, run_pipeline_wrapper
from services.pipeline import PipelineService
from services.early_warning.pipeline import EarlyWarningPipelineService

# Module logger
LOGGER = logging.getLogger(__name__)

# Local hour (0–23) for the daily scheduled pipeline run
DAILY_PIPELINE_HOUR = 3
# Local minute (0–59) for the daily scheduled pipeline run
DAILY_PIPELINE_MINUTE = 0


def seconds_until_next_daily_pipeline_run(now: datetime | None = None) -> float:
    """Compute seconds until the next daily pipeline run time.

    Args:
        now: Optional reference datetime; defaults to ``datetime.now()``.

    Returns:
        Number of seconds until today or tomorrow at
        ``DAILY_PIPELINE_HOUR``:``DAILY_PIPELINE_MINUTE``.
    """
    current = now or datetime.now()
    next_run = datetime.combine(current.date(), time(DAILY_PIPELINE_HOUR, DAILY_PIPELINE_MINUTE))
    if current >= next_run:
        next_run += timedelta(days=1)
    return (next_run - current).total_seconds()


async def _daily_pipeline_loop(
    pipeline_service: PipelineService, stop_event: asyncio.Event
) -> None:
    """Loop that waits until the daily time, then runs the official pipeline.

    Exits when ``stop_event`` is set (including while waiting for the next run).

    Args:
        pipeline_service: Service that executes the official recall pipeline.
        stop_event: Event set by the stop helper to terminate the loop.
    """
    while not stop_event.is_set():
        delay = seconds_until_next_daily_pipeline_run()
        LOGGER.info(
            "Next scheduled pipeline run in %.0f second(s) (daily at %02d:%02d)",
            delay,
            DAILY_PIPELINE_HOUR,
            DAILY_PIPELINE_MINUTE
        )

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=delay)
            break
        except TimeoutError:
            pass

        if stop_event.is_set():
            break

        await run_pipeline_wrapper(pipeline_service, context="scheduled")


def start_daily_pipeline_scheduler(
    pipeline_service: PipelineService,
    *,
    enabled: bool = True,
) -> tuple[asyncio.Task[None] | None, asyncio.Event | None]:
    """Start the daily official-pipeline background scheduler.

    Args:
        pipeline_service: Service that executes the official recall pipeline.
        enabled: When False, does not start a task and returns ``(None, None)``.

    Returns:
        Tuple of ``(task, stop_event)`` for a running scheduler, or
        ``(None, None)`` when disabled.
    """
    if not enabled:
        LOGGER.info("Official daily pipeline scheduler is disabled")
        return None, None
    stop_event = asyncio.Event()
    task = asyncio.create_task(
        _daily_pipeline_loop(pipeline_service, stop_event),
        name="daily-pipeline-scheduler",
    )
    return task, stop_event


async def stop_daily_pipeline_scheduler(
    task: asyncio.Task[None] | None,
    stop_event: asyncio.Event | None,
) -> None:
    """Stop the daily official-pipeline scheduler if it is running.

    Args:
        task: Background task returned by ``start_daily_pipeline_scheduler``.
        stop_event: Stop event returned by ``start_daily_pipeline_scheduler``.
    """
    if task is None or stop_event is None:
        return
    stop_event.set()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def _early_warning_loop(
    pipeline_service: EarlyWarningPipelineService,
    stop_event: asyncio.Event,
) -> None:
    """Loop that waits until the daily time, then runs early-warning discovery.

    Exits when ``stop_event`` is set (including while waiting for the next run).

    Args:
        pipeline_service: Service that executes early-warning discovery.
        stop_event: Event set by the stop helper to terminate the loop.
    """
    while not stop_event.is_set():
        delay = seconds_until_next_daily_pipeline_run()
        LOGGER.info(
            "Next scheduled early-warning run in %.0f second(s) (daily at %02d:%02d)",
            delay,
            DAILY_PIPELINE_HOUR,
            DAILY_PIPELINE_MINUTE,
        )

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=delay)
            break
        except TimeoutError:
            pass

        if stop_event.is_set():
            break

        await run_early_warning_wrapper(pipeline_service)


def start_early_warning_scheduler(
    pipeline_service: EarlyWarningPipelineService,
) -> tuple[asyncio.Task[None] | None, asyncio.Event | None]:
    """Start the daily early-warning background scheduler.

    Does nothing when early warning is disabled in the pipeline service config.

    Args:
        pipeline_service: Service that executes early-warning discovery.

    Returns:
        Tuple of ``(task, stop_event)`` for a running scheduler, or
        ``(None, None)`` when early warning is disabled.
    """
    if not pipeline_service.config.enabled:
        return None, None
    stop_event = asyncio.Event()
    task = asyncio.create_task(
        _early_warning_loop(pipeline_service, stop_event),
        name="early-warning-scheduler",
    )
    return task, stop_event


async def stop_early_warning_scheduler(
    task: asyncio.Task[None] | None,
    stop_event: asyncio.Event | None,
) -> None:
    """Stop the early-warning scheduler if it is running.

    Args:
        task: Background task returned by ``start_early_warning_scheduler``.
        stop_event: Stop event returned by ``start_early_warning_scheduler``.
    """
    if task is None or stop_event is None:
        return
    stop_event.set()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
