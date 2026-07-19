from __future__ import annotations

import logging

from fastapi import Depends

from settings import get_settings
from db.chroma_client import FoodRecallAlertsChromaClient
from db.chroma_source_client import InMemoryScraperSourceConfigStore, ScraperSourceConfigChromaClient
from db.chroma_warnings_client import InMemoryPipelineWarningsStore, PipelineWarningsChromaClient
from db.interface import FoodRecallAlertsDBInterface
from db.source_config_interface import ScraperSourceConfigDBInterface
from db.warnings_interface import PipelineWarningsDBInterface
from services.alert_events import AlertChangeBroadcaster
from services.alerts import AlertsService
from services.pipeline import PipelineService
from services.pipeline_progress import PipelineProgressTracker
from services.source_bootstrap import ensure_bootstrap_sources
from services.sources import SourcesService
from services.warnings import WarningsService
from models.food_recall_alert import set_country_source_lookup
from models.pipeline_options import set_source_names_provider

LOGGER = logging.getLogger(__name__)

_settings = get_settings()


def _build_source_config_db() -> ScraperSourceConfigDBInterface:
    try:
        client = ScraperSourceConfigChromaClient(
            host=_settings.chroma_host,
            port=_settings.chroma_port,
        )
        ensure_bootstrap_sources(client)
        return client
    except Exception as exc:  # noqa: BLE001 - fall back so local tests/dev can start
        LOGGER.warning("Falling back to in-memory source registry: %s", exc)
        store = InMemoryScraperSourceConfigStore()
        ensure_bootstrap_sources(store)
        return store


def _build_warnings_db() -> PipelineWarningsDBInterface:
    try:
        return PipelineWarningsChromaClient(
            host=_settings.chroma_host,
            port=_settings.chroma_port,
        )
    except Exception as exc:  # noqa: BLE001 - fall back so local tests/dev can start
        LOGGER.warning("Falling back to in-memory pipeline warnings store: %s", exc)
        return InMemoryPipelineWarningsStore()


_chroma_client: FoodRecallAlertsDBInterface = FoodRecallAlertsChromaClient(
    host=_settings.chroma_host,
    port=_settings.chroma_port,
)
_source_config_db: ScraperSourceConfigDBInterface = _build_source_config_db()
_warnings_db: PipelineWarningsDBInterface = _build_warnings_db()
_pipeline_progress_tracker = PipelineProgressTracker()
_alert_change_broadcaster = AlertChangeBroadcaster()
_warnings_service = WarningsService(_warnings_db)


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


def get_warnings_db() -> PipelineWarningsDBInterface:
    return _warnings_db


def get_warnings_service() -> WarningsService:
    return _warnings_service


def get_pipeline_service(
    db: FoodRecallAlertsDBInterface = Depends(get_db),
    source_db: ScraperSourceConfigDBInterface = Depends(get_source_config_db),
    alert_broadcaster: AlertChangeBroadcaster = Depends(get_alert_change_broadcaster),
    warnings_service: WarningsService = Depends(get_warnings_service),
) -> PipelineService:
    return PipelineService(
        db,
        source_db,
        progress_tracker=_pipeline_progress_tracker,
        alert_broadcaster=alert_broadcaster,
        warnings_service=warnings_service,
    )
