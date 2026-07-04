import os

from fastapi import Depends

from db.interface import FoodRecallAlertsDBInterface
from db.chroma_client import FoodRecallAlertsChromaClient
from services.alerts import AlertsService
from services.pipeline_progress import PipelineProgressTracker
from services.pipeline import PipelineService

_chroma_client: FoodRecallAlertsDBInterface = FoodRecallAlertsChromaClient(
    host=os.getenv("CHROMA_HOST", "localhost"),
    port=int(os.getenv("CHROMA_PORT", "8000")),
)
_pipeline_progress_tracker = PipelineProgressTracker()

def get_db() -> FoodRecallAlertsDBInterface:
    return _chroma_client

def get_alerts_service(db: FoodRecallAlertsDBInterface = Depends(get_db)) -> AlertsService:
    return AlertsService(db)

def get_pipeline_service(db: FoodRecallAlertsDBInterface = Depends(get_db)) -> PipelineService:
    return PipelineService(db, progress_tracker=_pipeline_progress_tracker)