from fastapi import APIRouter, Depends, status, HTTPException

from services.pipeline import PipelineService
from dependencies import get_pipeline_service

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])

@router.post("/run", response_model=dict, status_code=status.HTTP_200_OK)
async def run_pipeline(pipeline_service: PipelineService = Depends(get_pipeline_service)) -> dict:
    try:
        count = await pipeline_service.run_pipeline()

        return {
            "status": "success",
            "message": "AI Agents Pipeline executed successfully",
            "new_alerts_count": count
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))