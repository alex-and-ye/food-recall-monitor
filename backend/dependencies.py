import os

from fastapi import Depends

from db.interface import FoodRecallAlertsDBInterface
from db.chroma_client import FoodRecallAlertsChromaClient
from services.alerts import AlertsService
from services.pipeline import PipelineService

_chroma_client: FoodRecallAlertsDBInterface = FoodRecallAlertsChromaClient()

def get_db() -> FoodRecallAlertsDBInterface:
    return _chroma_client

def get_alerts_service(db: FoodRecallAlertsDBInterface = Depends(get_db)) -> AlertsService:
    return AlertsService(db)

def get_pipeline_service(db: FoodRecallAlertsDBInterface = Depends(get_db)) -> PipelineService:
    return PipelineService(db)