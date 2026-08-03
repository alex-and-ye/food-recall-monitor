"""HTTP routes for pipeline warning listing and acknowledgement."""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from dependencies import get_warnings_service
from models.pipeline_warning import PipelineWarning, PipelineWarningsSummary
from services.warnings import WarningsService

# FastAPI router for pipeline warning endpoints
router = APIRouter(prefix="/api/warnings", tags=["warnings"])


@router.get("", response_model=list[PipelineWarning])
def list_warnings(
    acknowledged: bool | None = Query(default=None),
    warnings_service: WarningsService = Depends(get_warnings_service),
) -> list[PipelineWarning]:
    """List pipeline warnings, optionally filtered by acknowledgement.

    Args:
        acknowledged: When set, filter to acknowledged (True) or
            unacknowledged (False) warnings only.
        warnings_service: Injected warnings service.

    Returns:
        List of matching ``PipelineWarning`` records.
    """
    return warnings_service.list_warnings(acknowledged=acknowledged)


@router.get("/summary", response_model=PipelineWarningsSummary)
def get_warnings_summary(
    warnings_service: WarningsService = Depends(get_warnings_service),
) -> PipelineWarningsSummary:
    """Return aggregate counts for pipeline warnings.

    Args:
        warnings_service: Injected warnings service.

    Returns:
        ``PipelineWarningsSummary`` totals.
    """
    return warnings_service.get_summary()


@router.post("/acknowledge-all", response_model=dict)
def acknowledge_all_warnings(
    warnings_service: WarningsService = Depends(get_warnings_service),
) -> dict:
    """Acknowledge every unacknowledged pipeline warning.

    Args:
        warnings_service: Injected warnings service.

    Returns:
        Dict with ``acknowledged_count`` set to the number updated.
    """
    updated = warnings_service.acknowledge_all()
    return {"acknowledged_count": updated}


@router.post("/{warning_id}/acknowledge", response_model=PipelineWarning)
def acknowledge_warning(
    warning_id: str,
    warnings_service: WarningsService = Depends(get_warnings_service),
) -> PipelineWarning:
    """Acknowledge a single pipeline warning by id.

    Args:
        warning_id: Unique warning id.
        warnings_service: Injected warnings service.

    Returns:
        Updated ``PipelineWarning``.

    Raises:
        HTTPException: 404 if the warning id is unknown.
    """
    updated = warnings_service.acknowledge(warning_id)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown warning: {warning_id}",
        )
    return updated
