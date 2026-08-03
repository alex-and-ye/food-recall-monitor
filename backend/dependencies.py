"""FastAPI dependency providers and process-wide service wiring.

Builds Chroma-backed (or in-memory fallback) stores, early-warning services,
and shared locks/broadcasters once at import time. Exposes ``get_*`` helpers
for use with ``Depends`` in route handlers.
"""

import asyncio
import logging

from fastapi import Depends

from settings import get_settings
from db.chroma_client import FoodRecallAlertsChromaClient
from db.chroma_source_client import InMemoryScraperSourceConfigStore, ScraperSourceConfigChromaClient
from db.chroma_warnings_client import InMemoryPipelineWarningsStore, PipelineWarningsChromaClient
from db.chroma_pipeline_logs_client import (
    InMemoryPipelineRunLogsStore,
    PipelineRunLogsChromaClient,
)
from db.chroma_early_warning_candidates import (
    EarlyWarningCandidatesChromaClient,
    InMemoryEarlyWarningCandidateStore,
)
from db.chroma_early_warning_client import (
    EarlyWarningIncidentsChromaClient,
    InMemoryEarlyWarningIncidentStore,
)
from db.interface import FoodRecallAlertsDBInterface
from db.pipeline_logs_interface import PipelineRunLogsDBInterface
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

# Module logger
LOGGER = logging.getLogger(__name__)

# Cached application settings
_settings = get_settings()
# Official / early-warning enablement switches from pipelines.yaml
_pipeline_switches = load_pipeline_switches(_settings.pipeline_switches_path)
# Early-warning YAML config with runtime ``enabled`` from pipeline switches
_early_warning_config = load_early_warning_config(_settings.early_warning_config_path).model_copy(
    update={"enabled": _pipeline_switches.early_warning.enabled}
)
_early_warning_config.validate_runtime(brave_api_key=_settings.brave_api_key)


def _build_source_config_db() -> ScraperSourceConfigDBInterface:
    """Create the scraper source-config store, with in-memory fallback.

    Returns:
        Chroma-backed store when available; otherwise an in-memory store.
        Bootstrap sources are ensured in either case.
    """
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
    """Create the pipeline warnings store, with in-memory fallback.

    Returns:
        Chroma-backed warnings store, or an in-memory store on failure.
    """
    try:
        return PipelineWarningsChromaClient(
            host=_settings.chroma_host,
            port=_settings.chroma_port,
        )
    except Exception as exc:  # noqa: BLE001 - fall back so local tests/dev can start
        LOGGER.warning("Falling back to in-memory pipeline warnings store: %s", exc)
        return InMemoryPipelineWarningsStore()


def _build_pipeline_logs_db() -> PipelineRunLogsDBInterface:
    """Create the pipeline run-logs store, with in-memory fallback.

    Returns:
        Chroma-backed run-logs store, or an in-memory store on failure.
    """
    try:
        return PipelineRunLogsChromaClient(
            host=_settings.chroma_host,
            port=_settings.chroma_port,
        )
    except Exception as exc:  # noqa: BLE001 - fall back so local tests/dev can start
        LOGGER.warning("Falling back to in-memory pipeline run logs store: %s", exc)
        return InMemoryPipelineRunLogsStore()


def _build_early_warning_candidate_db():
    """Create the early-warning candidates store, with in-memory fallback.

    Returns:
        Chroma-backed candidates store, or an in-memory store on failure.
    """
    try:
        return EarlyWarningCandidatesChromaClient(
            host=_settings.chroma_host,
            port=_settings.chroma_port,
        )
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Falling back to in-memory early-warning candidates: %s", exc)
        return InMemoryEarlyWarningCandidateStore()


def _build_early_warning_incident_db():
    """Create the early-warning incidents store, with in-memory fallback.

    Returns:
        Chroma-backed incidents store, or an in-memory store on failure.
    """
    try:
        return EarlyWarningIncidentsChromaClient(
            host=_settings.chroma_host,
            port=_settings.chroma_port,
        )
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Falling back to in-memory early-warning incidents: %s", exc)
        return InMemoryEarlyWarningIncidentStore()


# Food recall alerts Chroma client
_chroma_client: FoodRecallAlertsDBInterface = FoodRecallAlertsChromaClient(
    host=_settings.chroma_host,
    port=_settings.chroma_port,
)
# Scraper source registry store
_source_config_db: ScraperSourceConfigDBInterface = _build_source_config_db()
# Pipeline warnings store
_warnings_db: PipelineWarningsDBInterface = _build_warnings_db()
# Early-warning discovery candidates store
_early_warning_candidate_db = _build_early_warning_candidate_db()
# Early-warning incidents store
_early_warning_incident_db = _build_early_warning_incident_db()
# Pipeline run logs store
_pipeline_logs_db = _build_pipeline_logs_db()
# Tracks in-flight pipeline progress for API consumers
_pipeline_progress_tracker = PipelineProgressTracker(_pipeline_logs_db)
# SSE broadcaster for official alert changes
_alert_change_broadcaster = AlertChangeBroadcaster()
# SSE broadcaster for early-warning incident changes
_incident_change_broadcaster = AlertChangeBroadcaster()
# Shared warnings service instance
_warnings_service = WarningsService(_warnings_db)
# Mutual exclusion lock shared by official and early-warning pipeline runs
_pipeline_run_lock = asyncio.Lock()
# Semantic matching subsection of early-warning config
_semantic_config = _early_warning_config.semantic_matching
# Optional embedding index for incident/alert similarity (None if disabled/failed)
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
# Incident confidence scoring subsection of early-warning config
_confidence_values = _early_warning_config.incident_confidence
# Policy used to score early-warning incident confidence
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
# Early-warning incident CRUD / merge service
_early_warning_incident_service = EarlyWarningIncidentService(
    _early_warning_incident_db,
    confidence_policy=_confidence_policy,
    semantic_index=_semantic_index,
    semantic_review_threshold=_semantic_config.review_threshold,
    semantic_auto_merge_threshold=_semantic_config.auto_merge_threshold,
    semantic_result_limit=_semantic_config.result_limit,
)
# Links early-warning incidents to official alerts for verification
_incident_verification_service = IncidentVerificationService(
    _early_warning_incident_db,
    _chroma_client,
)
# LangGraph-style processing for early-warning candidates
_early_warning_processing_service = EarlyWarningProcessingService()
# Brave Search client when early warning is enabled; otherwise None
_brave_search_client = (
    BraveSearchClient(
        _settings.brave_api_key or "",
        config=_early_warning_config.brave,
        base_url=_settings.brave_search_base_url,
    )
    if _early_warning_config.enabled
    else None
)
# Orchestrates early-warning discovery runs
_early_warning_pipeline_service = EarlyWarningPipelineService(
    config=_early_warning_config,
    search_client=_brave_search_client,
    candidate_store=_early_warning_candidate_db,
    incident_service=_early_warning_incident_service,
    processing_service=_early_warning_processing_service,
    verification_service=_incident_verification_service,
    broadcaster=_incident_change_broadcaster,
    warnings_service=_warnings_service,
    progress_tracker=_pipeline_progress_tracker,
    run_lock=_pipeline_run_lock,
)


def get_pipeline_logs_db() -> PipelineRunLogsDBInterface:
    """Provide the process-wide pipeline run-logs store.

    Returns:
        Pipeline run logs database interface.
    """
    return _pipeline_logs_db


def get_pipeline_progress_tracker() -> PipelineProgressTracker:
    """Provide the shared pipeline progress tracker.

    Returns:
        Tracker used to report in-flight pipeline progress.
    """
    return _pipeline_progress_tracker


def _country_source_from_registry(source_name: str) -> str | None:
    """Look up ``country_source`` for a registered scraper source name.

    Args:
        source_name: Registry key for the scraper source.

    Returns:
        Country source label, or ``None`` if the source is unknown.
    """
    document = _source_config_db.get_source(source_name)
    if document is None:
        return None
    return document.country_source


set_country_source_lookup(_country_source_from_registry)
set_source_names_provider(_source_config_db.list_source_names)


def get_db() -> FoodRecallAlertsDBInterface:
    """Provide the food recall alerts database client.

    Returns:
        Alerts store interface.
    """
    return _chroma_client


def get_source_config_db() -> ScraperSourceConfigDBInterface:
    """Provide the scraper source-config store.

    Returns:
        Source registry database interface.
    """
    return _source_config_db


def get_alerts_service(db: FoodRecallAlertsDBInterface = Depends(get_db)) -> AlertsService:
    """Build an ``AlertsService`` for the current request.

    Args:
        db: Injected alerts database interface.

    Returns:
        Alerts service bound to ``db``.
    """
    return AlertsService(db)


def get_alert_change_broadcaster() -> AlertChangeBroadcaster:
    """Provide the SSE broadcaster for official alert changes.

    Returns:
        Shared alert change broadcaster.
    """
    return _alert_change_broadcaster


def get_incident_change_broadcaster() -> AlertChangeBroadcaster:
    """Provide the SSE broadcaster for early-warning incident changes.

    Returns:
        Shared incident change broadcaster.
    """
    return _incident_change_broadcaster


def get_early_warning_incident_service() -> EarlyWarningIncidentService:
    """Provide the early-warning incident service singleton.

    Returns:
        Shared ``EarlyWarningIncidentService``.
    """
    return _early_warning_incident_service


def get_incident_verification_service() -> IncidentVerificationService:
    """Provide the incident verification service singleton.

    Returns:
        Shared ``IncidentVerificationService``.
    """
    return _incident_verification_service


def get_early_warning_pipeline_service() -> EarlyWarningPipelineService:
    """Provide the early-warning pipeline service singleton.

    Returns:
        Shared ``EarlyWarningPipelineService``.
    """
    return _early_warning_pipeline_service


def get_pipeline_switches():
    """Provide loaded official / early-warning pipeline switches.

    Returns:
        ``PipelineSwitches`` parsed from ``pipelines.yaml``.
    """
    return _pipeline_switches


def get_pipeline_run_lock() -> asyncio.Lock:
    """Provide the shared lock that serializes pipeline runs.

    Returns:
        Process-wide ``asyncio.Lock``.
    """
    return _pipeline_run_lock


def get_sources_service(
    source_db: ScraperSourceConfigDBInterface = Depends(get_source_config_db),
) -> SourcesService:
    """Build a ``SourcesService`` for the current request.

    Args:
        source_db: Injected source registry store.

    Returns:
        Sources service bound to ``source_db``.
    """
    return SourcesService(source_db)


def get_warnings_db() -> PipelineWarningsDBInterface:
    """Provide the pipeline warnings store.

    Returns:
        Warnings database interface.
    """
    return _warnings_db


def get_warnings_service() -> WarningsService:
    """Provide the shared warnings service singleton.

    Returns:
        Shared ``WarningsService``.
    """
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
    """Build a ``PipelineService`` wired to shared progress, lock, and index.

    Args:
        db: Alerts database interface.
        source_db: Scraper source registry store.
        alert_broadcaster: Broadcaster for official alert change events.
        warnings_service: Service for recording pipeline warnings.
        verification_service: Service linking incidents to official alerts.
        incident_broadcaster: Broadcaster for incident change events.

    Returns:
        Configured official ``PipelineService``.
    """
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
