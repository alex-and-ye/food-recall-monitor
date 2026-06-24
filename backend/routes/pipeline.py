from fastapi import APIRouter, Depends, status, HTTPException

from agents.errors import SourceFetchError
from dependencies import get_pipeline_progress_tracker
from models.pipeline_options import PipelineRunOptions
from services.pipeline import PipelineService
from services.pipeline_progress import PipelineProgressTracker
from dependencies import get_pipeline_service

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])

@router.post("/run", response_model=dict, status_code=status.HTTP_200_OK)
async def run_pipeline(
    options: PipelineRunOptions | None = None,
    pipeline_service: PipelineService = Depends(get_pipeline_service)
) -> dict:
    try:
        result = await pipeline_service.run_pipeline(options)
    except SourceFetchError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    if result.source_failures:
        return {
            "status": "partial_success",
            "message": "Pipeline completed with source fetch failures",
            "run_id": result.run_id,
            "progress_url": f"/api/pipeline/runs/{result.run_id}" if result.run_id else None,
            "new_alerts_count": result.new_alerts_count,
            "records_fetched": result.records_fetched,
            "source_failures": result.source_failures,
        }

    return {
        "status": "success",
        "message": "AI Agents Pipeline executed successfully",
        "run_id": result.run_id,
        "progress_url": f"/api/pipeline/runs/{result.run_id}" if result.run_id else None,
        "new_alerts_count": result.new_alerts_count,
        "records_fetched": result.records_fetched,
    }


@router.get("/runs", response_model=dict, status_code=status.HTTP_200_OK)
async def list_pipeline_runs(
    limit: int = 10,
    tracker: PipelineProgressTracker = Depends(get_pipeline_progress_tracker),
) -> dict:
    runs = tracker.list_runs(limit=limit)
    return {"runs": [run.model_dump() for run in runs]}


@router.get("/runs/{run_id}", response_model=dict, status_code=status.HTTP_200_OK)
async def get_pipeline_run(
    run_id: str,
    tracker: PipelineProgressTracker = Depends(get_pipeline_progress_tracker),
) -> dict:
    run = tracker.get_run(run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run not found: {run_id}",
        )
    return run.model_dump()


@router.get("/runs/{run_id}/events", response_model=dict, status_code=status.HTTP_200_OK)
async def get_pipeline_run_events(
    run_id: str,
    tracker: PipelineProgressTracker = Depends(get_pipeline_progress_tracker),
) -> dict:
    run = tracker.get_run(run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run not found: {run_id}",
        )
    return {
        "run_id": run.run_id,
        "status": run.status,
        "events": [event.model_dump() for event in run.events],
    }