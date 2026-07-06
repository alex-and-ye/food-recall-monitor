import asyncio
import logging

from pipeline_runner import run_pipeline_wrapper
from services.alerts import AlertsService
from services.pipeline import PipelineService

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
