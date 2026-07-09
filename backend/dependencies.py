import os

from fastapi import Depends

from db.interface import FoodRecallAlertsDBInterface
from db.chroma_client import FoodRecallAlertsChromaClient
from services.alert_events import AlertChangeBroadcaster
from services.alerts import AlertsService
from services.pipeline_progress import PipelineProgressTracker
from services.pipeline import PipelineService

_chroma_client: FoodRecallAlertsDBInterface = FoodRecallAlertsChromaClient(
    host=os.getenv("CHROMA_HOST", "localhost"),
    port=int(os.getenv("CHROMA_PORT", "8000")),
)
_pipeline_progress_tracker = PipelineProgressTracker()
_alert_change_broadcaster = AlertChangeBroadcaster()

def get_db() -> FoodRecallAlertsDBInterface:
    return _chroma_client

def get_alerts_service(db: FoodRecallAlertsDBInterface = Depends(get_db)) -> AlertsService:
    return AlertsService(db)

def get_alert_change_broadcaster() -> AlertChangeBroadcaster:
    return _alert_change_broadcaster

def get_pipeline_service(
    db: FoodRecallAlertsDBInterface = Depends(get_db),
    alert_broadcaster: AlertChangeBroadcaster = Depends(get_alert_change_broadcaster),
) -> PipelineService:
    return PipelineService(
        db,
        progress_tracker=_pipeline_progress_tracker,
        alert_broadcaster=alert_broadcaster,
    )