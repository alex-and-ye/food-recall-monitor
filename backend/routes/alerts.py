"""HTTP routes for food recall alerts.

Supports listing/search, stats, version, single-alert lookup, and SSE
change notifications.
"""

from datetime import date

from fastapi import APIRouter, Depends, status, HTTPException
from fastapi.responses import StreamingResponse
import json

from models.food_recall_alert import FoodRecallAlert, FoodRecallAlertStats, FoodRecallAlertsVersion
from models.sort_options import VALID_SORT_OPTIONS
from services.alert_events import AlertChangeBroadcaster
from services.alerts import AlertsService
from dependencies import get_alert_change_broadcaster, get_alerts_service

# FastAPI router for alert endpoints
router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("", response_model=dict, status_code=status.HTTP_200_OK)
async def get_alerts(
    search: str | None = None,
    risk_level: str | None = None,
    country_source: str | None = None,
    recall_date: date | None = None,
    sort_by: str | None = None,
    alerts_service: AlertsService = Depends(get_alerts_service),
) -> dict:
    """List all alerts, or search/filter when query params are provided.

    Args:
        search: Free-text search query.
        risk_level: Optional risk-level filter.
        country_source: Optional country/source filter.
        recall_date: Optional recall date filter.
        sort_by: Optional sort key; must be in ``VALID_SORT_OPTIONS``.
        alerts_service: Injected alerts service.

    Returns:
        Dict with an ``alerts`` list of matching ``FoodRecallAlert`` records.

    Raises:
        HTTPException: 422 if ``sort_by`` is invalid; 500 on unexpected errors.
    """
    try:
        normalized_sort_by = sort_by.strip().lower() if sort_by and sort_by.strip() else None
        if normalized_sort_by is not None and normalized_sort_by not in VALID_SORT_OPTIONS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"sort_by must be one of: {', '.join(sorted(VALID_SORT_OPTIONS))}",
            )

        has_query = any(
            [
                search,
                risk_level,
                country_source,
                recall_date,
                normalized_sort_by,
            ]
        )
        if has_query:
            alerts = alerts_service.search_alerts(
                search=search,
                risk_level=risk_level,
                country_source=country_source,
                recall_date=recall_date,
                sort_by=normalized_sort_by,
            )
        else:
            alerts = alerts_service.get_alerts()

        return {
            "alerts": alerts
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/stats", response_model=FoodRecallAlertStats, status_code=status.HTTP_200_OK)
async def get_alert_stats(
    alerts_service: AlertsService = Depends(get_alerts_service),
) -> FoodRecallAlertStats:
    """Return aggregate statistics for stored alerts.

    Args:
        alerts_service: Injected alerts service.

    Returns:
        ``FoodRecallAlertStats`` summary.

    Raises:
        HTTPException: 500 on unexpected errors.
    """
    try:
        return alerts_service.get_alert_stats()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/version", response_model=FoodRecallAlertsVersion, status_code=status.HTTP_200_OK)
async def get_alerts_version(
    alerts_service: AlertsService = Depends(get_alerts_service),
) -> FoodRecallAlertsVersion:
    """Return the current alerts dataset version token.

    Args:
        alerts_service: Injected alerts service.

    Returns:
        ``FoodRecallAlertsVersion`` used by clients for cache invalidation.

    Raises:
        HTTPException: 500 on unexpected errors.
    """
    try:
        return alerts_service.get_alerts_version()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/events")
async def stream_alert_events(
    alert_broadcaster: AlertChangeBroadcaster = Depends(get_alert_change_broadcaster),
) -> StreamingResponse:
    """Stream server-sent events when alerts change.

    Emits ``alerts-changed`` events with ``saved_count``, plus SSE comments
    as keepalives.

    Args:
        alert_broadcaster: Injected alert change broadcaster.

    Returns:
        ``StreamingResponse`` with ``text/event-stream`` media type.
    """
    async def event_stream():
        """Yield SSE frames for alert changes and keepalives.

        Yields:
            Encoded SSE strings for keepalives or ``alerts-changed`` events.
        """
        async for event in alert_broadcaster.iter_with_keepalive():
            if event is None:
                yield ": keepalive\n\n"
                continue

            payload = json.dumps({"saved_count": event.saved_count})
            yield f"event: alerts-changed\ndata: {payload}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{alert_id}", response_model=FoodRecallAlert, status_code=status.HTTP_200_OK)
async def get_alert_by_id(
    alert_id: str,
    alerts_service: AlertsService = Depends(get_alerts_service),
) -> FoodRecallAlert:
    """Fetch a single alert by its identifier.

    Args:
        alert_id: Unique alert id.
        alerts_service: Injected alerts service.

    Returns:
        Matching ``FoodRecallAlert``.

    Raises:
        HTTPException: 404 if not found; 500 on unexpected errors.
    """
    try:
        alert = alerts_service.get_alert_by_id(alert_id)
        if alert is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
        return alert
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
