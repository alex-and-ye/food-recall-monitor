from fastapi import APIRouter, Depends
from fastapi import status, HTTPException

from models.pipeline_options import PipelineRunOptions
from services.pipeline_service import PipelineService
from config import get_pipeline_service

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])

@router.post("/run", response_model=dict, status_code=status.HTTP_200_OK)
async def run_pipeline(
    options: PipelineRunOptions | None = None,
    pipeline_service: PipelineService = Depends(get_pipeline_service)
) -> dict:
    try:
        count = await pipeline_service.run_pipeline(options)

        return {
            "status": "success",
            "message": "AI Agents Pipeline executed successfully",
            "new_alerts_count": count
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))