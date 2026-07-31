import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from dependencies import get_early_warning_incident_service, get_incident_change_broadcaster
from models.early_warning_incident import (
    EarlyWarningIncident,
    IncidentStatusCounts,
    IncidentType,
    IncidentsVersion,
    SourceKind,
    VerificationStatus,
)
from services.alert_events import AlertChangeBroadcaster
from services.early_warning.incidents import EarlyWarningIncidentService

router = APIRouter(prefix="/api/incidents", tags=["early warnings"])
VALID_SORTS = {"latest", "oldest", "confidence_high", "confidence_low"}

@router.get("", response_model=dict, status_code=status.HTTP_200_OK)
async def list_incidents(
    search: str | None = None,
    verification_status: VerificationStatus | None = None,
    incident_type: IncidentType | None = None,
    minimum_confidence: int | None = None,
    country: str | None = None,
    source_kind: SourceKind | None = None,
    publication_date: date | None = None,
    sort_by: str | None = None,
    service: EarlyWarningIncidentService = Depends(get_early_warning_incident_service),
) -> dict[str, list[EarlyWarningIncident]]:
    if minimum_confidence is not None and not 0 <= minimum_confidence <= 100:
        raise HTTPException(status_code=422, detail="minimum_confidence must be between 0 and 100")
    normalized_sort = sort_by.strip().lower() if sort_by else None
    if normalized_sort is not None and normalized_sort not in VALID_SORTS:
        raise HTTPException(
            status_code=422,
            detail=f"sort_by must be one of: {', '.join(sorted(VALID_SORTS))}",
        )
    return {
        "incidents": service.list_incidents(
            search=search,
            verification_status=verification_status,
            incident_type=incident_type,
            minimum_confidence=minimum_confidence,
            country=country,
            source_kind=source_kind,
            publication_date=publication_date,
            sort_by=normalized_sort,
        )
    }

@router.get("/stats", response_model=IncidentStatusCounts)
async def incident_stats(
    service: EarlyWarningIncidentService = Depends(get_early_warning_incident_service),
) -> IncidentStatusCounts:
    return service.get_status_counts()

@router.get("/version", response_model=IncidentsVersion)
async def incident_version(
    service: EarlyWarningIncidentService = Depends(get_early_warning_incident_service),
) -> IncidentsVersion:
    return service.get_version()

@router.get("/events")
async def stream_incident_events(
    broadcaster: AlertChangeBroadcaster = Depends(get_incident_change_broadcaster),
) -> StreamingResponse:
    async def event_stream():
        async for event in broadcaster.iter_with_keepalive():
            if event is None:
                yield ": keepalive\n\n"
            else:
                payload = json.dumps({"saved_count": event.saved_count})
                yield f"event: incidents-changed\ndata: {payload}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

@router.get("/{incident_id}", response_model=EarlyWarningIncident)
async def get_incident(
    incident_id: str,
    service: EarlyWarningIncidentService = Depends(get_early_warning_incident_service),
) -> EarlyWarningIncident:
    incident = service.get_incident(incident_id)
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    return incident
