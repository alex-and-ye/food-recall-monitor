import os

from fastapi import Depends

from db.interface import FoodRecallAlertsDBInterface
from db.chroma_client import FoodRecallAlertsChromaClient
from services.alerts import AlertsService
from services.pipeline import PipelineService

_db_client: FoodRecallAlertsDBInterface = FoodRecallAlertsChromaClient(os.path.join(os.getcwd(), "data", "chroma_db"))

def get_db() -> FoodRecallAlertsDBInterface:
    return _db_client

def get_alerts_service(db: FoodRecallAlertsDBInterface = Depends(get_db)) -> AlertsService:
    return AlertsService(db)

def get_pipeline_service(db: FoodRecallAlertsDBInterface = Depends(get_db)) -> PipelineService:
    return PipelineService(db)