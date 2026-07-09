import asyncio
import json
import logging

from fastapi import APIRouter, Depends, status, HTTPException
from fastapi.responses import StreamingResponse

from models.pipeline_options import PipelineRunOptions
from models.pipeline_run_status import PipelineProgressSnapshot, PipelineRunStartResponse
from services.pipeline import PipelineService
from services.pipeline_events import PipelineProgressBroadcaster
from services.pipeline_progress import PipelineProgressTracker
from dependencies import (
    get_pipeline_progress_broadcaster,
    get_pipeline_progress_tracker,
    get_pipeline_service,
)

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])

# TODO: Remove this manual trigger route before final project delivery
@router.post("/run", response_model=PipelineRunStartResponse, status_code=status.HTTP_202_ACCEPTED)
async def run_pipeline(
    options: PipelineRunOptions | None = None,
    pipeline_service: PipelineService = Depends(get_pipeline_service),
    progress_tracker: PipelineProgressTracker = Depends(get_pipeline_progress_tracker),
) -> PipelineRunStartResponse:
    if progress_tracker.is_running():
        snapshot = progress_tracker.get_snapshot()
        if snapshot.run_id is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A pipeline run is already in progress",
            )
        return PipelineRunStartResponse(
            run_id=snapshot.run_id,
            status="already_running",
            message="A pipeline run is already in progress",
        )

    run_options = options or PipelineRunOptions()
    run_id = progress_tracker.start_run(run_options)
    asyncio.create_task(
        _execute_pipeline_run(
            pipeline_service=pipeline_service,
            progress_tracker=progress_tracker,
            run_id=run_id,
            options=run_options,
        ),
        name=f"manual-pipeline-run-{run_id[:8]}",
    )
    return PipelineRunStartResponse(
        run_id=run_id,
        status="started",
        message="Pipeline run started",
    )


@router.get("/progress", response_model=PipelineProgressSnapshot, status_code=status.HTTP_200_OK)
async def get_pipeline_progress(
    progress_tracker: PipelineProgressTracker = Depends(get_pipeline_progress_tracker),
) -> PipelineProgressSnapshot:
    return progress_tracker.get_snapshot()


@router.get("/events")
async def stream_pipeline_events(
    progress_tracker: PipelineProgressTracker = Depends(get_pipeline_progress_tracker),
    progress_broadcaster: PipelineProgressBroadcaster = Depends(get_pipeline_progress_broadcaster),
) -> StreamingResponse:
    async def event_stream():
        snapshot = progress_tracker.get_snapshot()
        yield _sse_event("pipeline-progress", snapshot.model_dump(mode="json"))

        async for event in progress_broadcaster.iter_with_keepalive():
            if event is None:
                yield ": keepalive\n\n"
                continue
            yield _sse_event("pipeline-progress", event.model_dump(mode="json"))

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _execute_pipeline_run(
    *,
    pipeline_service: PipelineService,
    progress_tracker: PipelineProgressTracker,
    run_id: str,
    options: PipelineRunOptions,
) -> None:
    try:
        await pipeline_service.run_pipeline(options, run_id=run_id)
    except Exception:
        LOGGER.exception("Background pipeline run failed", extra={"run_id": run_id})
        # fail_run is handled inside PipelineService; keep a safety net if start failed early.
        if progress_tracker.is_running():
            snapshot = progress_tracker.get_snapshot()
            if snapshot.run_id == run_id:
                progress_tracker.fail_run(run_id=run_id, error="Pipeline run failed unexpectedly")


def _sse_event(event_name: str, payload: dict) -> str:
    return f"event: {event_name}\ndata: {json.dumps(payload)}\n\n"
