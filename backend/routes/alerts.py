from fastapi import APIRouter, Depends, status, HTTPException

from models.food_recall_alert import FoodRecallAlert, FoodRecallAlertStats
from services.alerts import AlertsService
from dependencies import get_alerts_service

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