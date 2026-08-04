"""Startup bootstrap helpers for empty databases.

Triggers an initial official-pipeline or early-warning discovery run when
the corresponding store has no records yet.
"""

import asyncio
import logging

from pipeline_runner import run_early_warning_wrapper, run_pipeline_wrapper
from services.alerts import AlertsService
from services.pipeline import PipelineService
from services.early_warning.incidents import EarlyWarningIncidentService
from services.early_warning.pipeline import EarlyWarningPipelineService

# Module logger
LOGGER = logging.getLogger(__name__)


async def run_state_aware_bootstrap(
    alerts_service: AlertsService, pipeline_service: PipelineService
) -> None:
    """Bootstrap the official pipeline when the alerts database is empty.

    If no alerts exist, schedules a background pipeline run. Otherwise logs
    that existing records were found and returns without starting a run.

    Args:
        alerts_service: Service used to read alert store statistics.
        pipeline_service: Service that executes the official recall pipeline.
    """
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
    """Bootstrap early-warning discovery when the incidents database is empty.

    If no incidents exist, schedules a background discovery run. Otherwise
    logs that existing incidents were found and returns without starting a run.

    Args:
        incident_service: Service used to count stored early-warning incidents.
        pipeline_service: Service that executes early-warning discovery.
    """
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
