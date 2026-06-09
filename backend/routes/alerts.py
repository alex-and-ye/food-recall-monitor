from fastapi import APIRouter, Depends, status, HTTPException

from services.alerts import AlertsService
from dependencies import get_alerts_service

router = APIRouter(prefix="/api/alerts", tags=["alerts"])

@router.get("/", response_model=dict, status_code=status.HTTP_200_OK)
async def get_alerts(alerts_service: AlertsService = Depends(get_alerts_service)) -> dict:
    try:
        return {
            "alerts": alerts_service.get_alerts()
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get("/stats", response_model=dict, status_code=status.HTTP_200_OK)
async def get_alert_stats(alerts_service: AlertsService = Depends(get_alerts_service)) -> dict:
    try:
        return alerts_service.get_alert_stats()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))