from fastapi import Depends

from settings import get_settings
from db.interface import FoodRecallAlertsDBInterface
from db.chroma_client import FoodRecallAlertsChromaClient
from services.alert_events import AlertChangeBroadcaster
from services.alerts import AlertsService
from services.pipeline_progress import PipelineProgressTracker
from services.pipeline import PipelineService

_settings = get_settings()
_chroma_client: FoodRecallAlertsDBInterface = FoodRecallAlertsChromaClient(
    host=_settings.chroma_host,
    port=_settings.chroma_port,
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
