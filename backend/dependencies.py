from __future__ import annotations

import logging
import os

from fastapi import Depends

from db.chroma_client import FoodRecallAlertsChromaClient
from db.chroma_source_client import InMemoryScraperSourceConfigStore, ScraperSourceConfigChromaClient
from db.interface import FoodRecallAlertsDBInterface
from db.source_config_interface import ScraperSourceConfigDBInterface
from services.alert_events import AlertChangeBroadcaster
from services.alerts import AlertsService
from services.pipeline import PipelineService
from services.pipeline_progress import PipelineProgressTracker
from services.source_bootstrap import ensure_bootstrap_sources
from services.sources import SourcesService
from models.food_recall_alert import set_country_source_lookup
from models.pipeline_options import set_source_names_provider

LOGGER = logging.getLogger(__name__)


def _build_source_config_db() -> ScraperSourceConfigDBInterface:
    host = os.getenv("CHROMA_HOST", "localhost")
    port = int(os.getenv("CHROMA_PORT", "8000"))
    try:
        client = ScraperSourceConfigChromaClient(host=host, port=port)
        ensure_bootstrap_sources(client)
        return client
    except Exception as exc:  # noqa: BLE001 - fall back so local tests/dev can start
        LOGGER.warning("Falling back to in-memory source registry: %s", exc)
        store = InMemoryScraperSourceConfigStore()
        ensure_bootstrap_sources(store)
        return store


_chroma_client: FoodRecallAlertsDBInterface = FoodRecallAlertsChromaClient(
    host=os.getenv("CHROMA_HOST", "localhost"),
    port=int(os.getenv("CHROMA_PORT", "8000")),
)
_source_config_db: ScraperSourceConfigDBInterface = _build_source_config_db()
_pipeline_progress_tracker = PipelineProgressTracker()
_alert_change_broadcaster = AlertChangeBroadcaster()


def _country_source_from_registry(source_name: str) -> str | None:
    document = _source_config_db.get_source(source_name)
    if document is None:
        return None
    return document.country_source


set_country_source_lookup(_country_source_from_registry)
set_source_names_provider(_source_config_db.list_source_names)


def get_db() -> FoodRecallAlertsDBInterface:
    return _chroma_client


def get_source_config_db() -> ScraperSourceConfigDBInterface:
    return _source_config_db


def get_alerts_service(db: FoodRecallAlertsDBInterface = Depends(get_db)) -> AlertsService:
    return AlertsService(db)


def get_alert_change_broadcaster() -> AlertChangeBroadcaster:
    return _alert_change_broadcaster


def get_sources_service(
    source_db: ScraperSourceConfigDBInterface = Depends(get_source_config_db),
) -> SourcesService:
    return SourcesService(source_db)


def get_pipeline_service(
    db: FoodRecallAlertsDBInterface = Depends(get_db),
    source_db: ScraperSourceConfigDBInterface = Depends(get_source_config_db),
    alert_broadcaster: AlertChangeBroadcaster = Depends(get_alert_change_broadcaster),
) -> PipelineService:
    return PipelineService(
        db,
        source_db,
        progress_tracker=_pipeline_progress_tracker,
        alert_broadcaster=alert_broadcaster,
    )
