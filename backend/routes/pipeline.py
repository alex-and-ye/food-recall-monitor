from fastapi import APIRouter, Depends, status, HTTPException

from agents.errors import SourceFetchError
from models.pipeline_options import PipelineRunOptions
from services.pipeline import PipelineService
from dependencies import get_pipeline_service

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])

# TODO: Remove this manual trigger route before final project delivery
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
            "new_alerts_count": result.new_alerts_count,
            "records_fetched": result.records_fetched,
            "source_failures": result.source_failures,
        }

    return {
        "status": "success",
        "message": "AI Agents Pipeline executed successfully",
        "new_alerts_count": result.new_alerts_count,
        "records_fetched": result.records_fetched,
    }
