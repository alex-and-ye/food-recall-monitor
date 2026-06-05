from fastapi import APIRouter, HTTPException, Depends, status
from backend.server.dependencies import get_db

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])

@router.post("/run", response_model=dict, status_code=status.HTTP_200_OK)
async def run_pipeline(db=Depends(get_db)) -> dict:
    try:
        # TODO: Trigger the AI Agents Pipeline here

        # TODO: Save the AI Agents Pipeline results to the database (DB must avoid saving duplicate results)

        return {
            "message": "AI Agents Pipeline executed successfully",
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))