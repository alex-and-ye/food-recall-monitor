from fastapi import APIRouter, Depends, HTTPException, status

from dependencies import get_early_warning_pipeline_service
from services.early_warning.pipeline import EarlyWarningPipelineService

router = APIRouter(prefix="/api/early-warnings", tags=["early warnings"])

@router.post("/run", status_code=status.HTTP_200_OK)
async def run_early_warning(
    dry_run: bool = False,
    service: EarlyWarningPipelineService = Depends(get_early_warning_pipeline_service),
) -> dict[str, object]:
    if not service.config.enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Early-warning discovery is disabled",
        )
    try:
        result = await service.run(dry_run=dry_run)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    return {
        "status": "partial_success" if result.failures else "success",
        **result.__dict__,
    }
