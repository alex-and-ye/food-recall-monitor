from __future__ import annotations

import asyncio
import logging

from fastapi import Depends

from settings import get_settings
from db.chroma_client import FoodRecallAlertsChromaClient
from db.chroma_source_client import InMemoryScraperSourceConfigStore, ScraperSourceConfigChromaClient
from db.chroma_warnings_client import InMemoryPipelineWarningsStore, PipelineWarningsChromaClient
from db.chroma_early_warning_candidates import (
    EarlyWarningCandidatesChromaClient,
    InMemoryEarlyWarningCandidateStore,
)
from db.chroma_early_warning_client import (
    EarlyWarningIncidentsChromaClient,
    InMemoryEarlyWarningIncidentStore,
)
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
from config.early_warning import load_early_warning_config
from config.pipelines import load_pipeline_switches
from services.early_warning.brave_search import BraveSearchClient
from services.early_warning.confidence import ConfidencePolicy, SOURCE_KIND_BASE_WEIGHTS
from services.early_warning.graph import EarlyWarningProcessingService
from services.early_warning.incidents import EarlyWarningIncidentService
from services.early_warning.pipeline import EarlyWarningPipelineService
from services.early_warning.semantic_index import SafetyEventSemanticIndex
from services.early_warning.verification import IncidentVerificationService
from models.food_recall_alert import set_country_source_lookup
from models.pipeline_options import set_source_names_provider

LOGGER = logging.getLogger(__name__)

_settings = get_settings()
_pipeline_switches = load_pipeline_switches(_settings.pipeline_switches_path)
_early_warning_config = load_early_warning_config(_settings.early_warning_config_path).model_copy(
    update={"enabled": _pipeline_switches.early_warning.enabled}
)
_early_warning_config.validate_runtime(brave_api_key=_settings.brave_api_key)


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


def _build_early_warning_candidate_db():
    try:
        return EarlyWarningCandidatesChromaClient(
            host=_settings.chroma_host,
            port=_settings.chroma_port,
        )
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Falling back to in-memory early-warning candidates: %s", exc)
        return InMemoryEarlyWarningCandidateStore()


def _build_early_warning_incident_db():
    try:
        return EarlyWarningIncidentsChromaClient(
            host=_settings.chroma_host,
            port=_settings.chroma_port,
        )
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Falling back to in-memory early-warning incidents: %s", exc)
        return InMemoryEarlyWarningIncidentStore()


_chroma_client: FoodRecallAlertsDBInterface = FoodRecallAlertsChromaClient(
    host=_settings.chroma_host,
    port=_settings.chroma_port,
)
_source_config_db: ScraperSourceConfigDBInterface = _build_source_config_db()
_warnings_db: PipelineWarningsDBInterface = _build_warnings_db()
_early_warning_candidate_db = _build_early_warning_candidate_db()
_early_warning_incident_db = _build_early_warning_incident_db()
_pipeline_progress_tracker = PipelineProgressTracker()
_alert_change_broadcaster = AlertChangeBroadcaster()
_incident_change_broadcaster = AlertChangeBroadcaster()
_warnings_service = WarningsService(_warnings_db)
_pipeline_run_lock = asyncio.Lock()
_semantic_config = _early_warning_config.semantic_matching
_semantic_index: SafetyEventSemanticIndex | None = None
if _semantic_config.enabled:
    try:
        _semantic_index = SafetyEventSemanticIndex(
            _settings.chroma_host,
            _settings.chroma_port,
            collection_name=_semantic_config.collection_name,
            model_name=_semantic_config.model_name,
        )
        _semantic_index.rebuild(
            incidents=_early_warning_incident_db.list_incidents(),
            official_alerts=_chroma_client.get_alerts(),
        )
    except Exception as exc:  # noqa: BLE001 - semantic index is optional/derived
        LOGGER.warning("Semantic safety-event index disabled: %s", exc)
_confidence_values = _early_warning_config.incident_confidence
_confidence_policy = ConfidencePolicy(
    base_weights={
        **SOURCE_KIND_BASE_WEIGHTS,
        **_confidence_values.source_kind_base_weights,
    },
    corroboration_per_source=_confidence_values.corroboration_per_source,
    corroboration_cap=_confidence_values.corroboration_cap,
    explicit_product_modifier=_confidence_values.explicit_product_modifier,
    explicit_hazard_modifier=_confidence_values.explicit_hazard_modifier,
    explicit_date_modifier=_confidence_values.explicit_date_modifier,
    trusted_domain_modifier=_confidence_values.trusted_domain_modifier,
    stale_reporting_modifier=_confidence_values.stale_reporting_modifier,
    vague_reporting_modifier=_confidence_values.vague_reporting_modifier,
    unofficial_cap=_confidence_values.unofficial_cap,
)
_early_warning_incident_service = EarlyWarningIncidentService(
    _early_warning_incident_db,
    confidence_policy=_confidence_policy,
    semantic_index=_semantic_index,
    semantic_review_threshold=_semantic_config.review_threshold,
    semantic_auto_merge_threshold=_semantic_config.auto_merge_threshold,
    semantic_result_limit=_semantic_config.result_limit,
)
_incident_verification_service = IncidentVerificationService(
    _early_warning_incident_db,
    _chroma_client,
)
_early_warning_processing_service = EarlyWarningProcessingService()
_brave_search_client = (
    BraveSearchClient(
        _settings.brave_api_key or "",
        config=_early_warning_config.brave,
        base_url=_settings.brave_search_base_url,
    )
    if _early_warning_config.enabled
    else None
)
_early_warning_pipeline_service = EarlyWarningPipelineService(
    config=_early_warning_config,
    search_client=_brave_search_client,
    candidate_store=_early_warning_candidate_db,
    incident_service=_early_warning_incident_service,
    processing_service=_early_warning_processing_service,
    verification_service=_incident_verification_service,
    broadcaster=_incident_change_broadcaster,
    warnings_service=_warnings_service,
    run_lock=_pipeline_run_lock,
)


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


def get_incident_change_broadcaster() -> AlertChangeBroadcaster:
    return _incident_change_broadcaster


def get_early_warning_incident_service() -> EarlyWarningIncidentService:
    return _early_warning_incident_service


def get_incident_verification_service() -> IncidentVerificationService:
    return _incident_verification_service


def get_early_warning_pipeline_service() -> EarlyWarningPipelineService:
    return _early_warning_pipeline_service


def get_pipeline_switches():
    return _pipeline_switches


def get_pipeline_run_lock() -> asyncio.Lock:
    return _pipeline_run_lock


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
    verification_service: IncidentVerificationService = Depends(
        get_incident_verification_service
    ),
    incident_broadcaster: AlertChangeBroadcaster = Depends(
        get_incident_change_broadcaster
    ),
) -> PipelineService:
    return PipelineService(
        db,
        source_db,
        progress_tracker=_pipeline_progress_tracker,
        alert_broadcaster=alert_broadcaster,
        warnings_service=warnings_service,
        verification_service=verification_service,
        incident_broadcaster=incident_broadcaster,
        run_lock=_pipeline_run_lock,
        semantic_index=_semantic_index,
    )
