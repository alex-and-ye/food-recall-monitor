from fastapi import APIRouter, Depends, status, HTTPException
from fastapi.responses import StreamingResponse
import json

from models.food_recall_alert import FoodRecallAlert, FoodRecallAlertStats, FoodRecallAlertsVersion
from services.alert_events import AlertChangeBroadcaster
from services.alerts import AlertsService
from dependencies import get_alert_change_broadcaster, get_alerts_service
router = APIRouter(prefix="/api/alerts", tags=["alerts"])

@router.get("", response_model=dict, status_code=status.HTTP_200_OK)
async def get_alerts(
    search: str | None = None,
    risk_level: str | None = None,
    country_source: str | None = None,
    alerts_service: AlertsService = Depends(get_alerts_service),
) -> dict:
    try:
        if search or risk_level or country_source:
            alerts = alerts_service.search_alerts(
                search=search,
                risk_level=risk_level,
                country_source=country_source,
            )
        else:
            alerts = alerts_service.get_alerts()

        return {
            "alerts": alerts
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get("/stats", response_model=FoodRecallAlertStats, status_code=status.HTTP_200_OK)
async def get_alert_stats(alerts_service: AlertsService = Depends(get_alerts_service)) -> FoodRecallAlertStats:
    try:
        return alerts_service.get_alert_stats()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get("/version", response_model=FoodRecallAlertsVersion, status_code=status.HTTP_200_OK)
async def get_alerts_version(alerts_service: AlertsService = Depends(get_alerts_service)) -> FoodRecallAlertsVersion:
    try:
        return alerts_service.get_alerts_version()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get("/events")
async def stream_alert_events(
    alert_broadcaster: AlertChangeBroadcaster = Depends(get_alert_change_broadcaster),
) -> StreamingResponse:
    async def event_stream():
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
async def get_alert_by_id(alert_id: str, alerts_service: AlertsService = Depends(get_alerts_service)) -> FoodRecallAlert:
    try:
        alert = alerts_service.get_alert_by_id(alert_id)
        if alert is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
        return alert
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))