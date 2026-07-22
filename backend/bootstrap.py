import asyncio
import logging

from pipeline_runner import run_early_warning_wrapper, run_pipeline_wrapper
from services.alerts import AlertsService
from services.pipeline import PipelineService
from services.early_warning.incidents import EarlyWarningIncidentService
from services.early_warning.pipeline import EarlyWarningPipelineService

LOGGER = logging.getLogger(__name__)


async def run_state_aware_bootstrap(alerts_service: AlertsService, pipeline_service: PipelineService) -> None:
    record_count = alerts_service.get_alert_stats().total_alerts
    if record_count == 0:
        LOGGER.info("Database is empty. Bootstrapping initial pipeline run...")
        asyncio.create_task(
            run_pipeline_wrapper(pipeline_service, context="bootstrap"),
            name="bootstrap-pipeline-run"
        )
        return

    LOGGER.info(
        "Database contains %d existing record(s). Scheduling next pipeline run...",
        record_count
    )


async def run_early_warning_bootstrap(
    incident_service: EarlyWarningIncidentService,
    pipeline_service: EarlyWarningPipelineService,
) -> None:
    incident_count = incident_service.store.count_incidents()
    if incident_count == 0:
        LOGGER.info(
            "Early-warning database is empty. Bootstrapping initial discovery run..."
        )
        asyncio.create_task(
            run_early_warning_wrapper(
                pipeline_service,
                context="bootstrap early-warning",
            ),
            name="bootstrap-early-warning-run",
        )
        return

    LOGGER.info(
        "Early-warning database contains %d existing incident(s). "
        "Scheduling next discovery run...",
        incident_count,
    )
