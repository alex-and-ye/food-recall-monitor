import asyncio
import logging
from datetime import datetime, time, timedelta

from pipeline_runner import run_pipeline_wrapper
from services.pipeline import PipelineService

LOGGER = logging.getLogger(__name__)

DAILY_PIPELINE_HOUR = 3
DAILY_PIPELINE_MINUTE = 0

def seconds_until_next_daily_pipeline_run(now: datetime | None = None) -> float:
    current = now or datetime.now()
    next_run = datetime.combine(current.date(), time(DAILY_PIPELINE_HOUR, DAILY_PIPELINE_MINUTE))
    if current >= next_run:
        next_run += timedelta(days=1)
    return (next_run - current).total_seconds()

async def _daily_pipeline_loop(pipeline_service: PipelineService, stop_event: asyncio.Event) -> None:
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

def start_daily_pipeline_scheduler(pipeline_service: PipelineService) -> tuple[asyncio.Task[None], asyncio.Event]:
    stop_event = asyncio.Event()
    task = asyncio.create_task(
        _daily_pipeline_loop(pipeline_service, stop_event), 
        name="daily-pipeline-scheduler"
    )
    return task, stop_event

async def stop_daily_pipeline_scheduler(task: asyncio.Task[None], stop_event: asyncio.Event) -> None:
    stop_event.set()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
