from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from dependencies import get_warnings_service
from models.pipeline_warning import PipelineWarning, PipelineWarningsSummary
from services.warnings import WarningsService

router = APIRouter(prefix="/api/warnings", tags=["warnings"])


@router.get("", response_model=list[PipelineWarning])
def list_warnings(
    acknowledged: bool | None = Query(default=None),
    warnings_service: WarningsService = Depends(get_warnings_service),
) -> list[PipelineWarning]:
    return warnings_service.list_warnings(acknowledged=acknowledged)


@router.get("/summary", response_model=PipelineWarningsSummary)
def get_warnings_summary(
    warnings_service: WarningsService = Depends(get_warnings_service),
) -> PipelineWarningsSummary:
    return warnings_service.get_summary()


@router.post("/acknowledge-all", response_model=dict)
def acknowledge_all_warnings(
    warnings_service: WarningsService = Depends(get_warnings_service),
) -> dict:
    updated = warnings_service.acknowledge_all()
    return {"acknowledged_count": updated}


@router.post("/{warning_id}/acknowledge", response_model=PipelineWarning)
def acknowledge_warning(
    warning_id: str,
    warnings_service: WarningsService = Depends(get_warnings_service),
) -> PipelineWarning:
    updated = warnings_service.acknowledge(warning_id)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown warning: {warning_id}",
        )
    return updated
