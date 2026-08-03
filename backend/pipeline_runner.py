"""Thin wrappers that run pipelines and log outcomes.

Used by bootstrap and schedulers so startup/scheduled runs share consistent
logging and error handling without raising into the caller.
"""

import logging

from models.pipeline_options import PipelineRunOptions
from services.pipeline import PipelineService
from services.early_warning.pipeline import EarlyWarningPipelineService

# Module logger
LOGGER = logging.getLogger(__name__)


async def run_pipeline_wrapper(
    pipeline_service: PipelineService,
    *,
    context: str,
    options: PipelineRunOptions | None = None,
) -> None:
    """Run the official recall pipeline and log success or failure.

    Exceptions are caught and logged so scheduled/bootstrap callers are not
    interrupted; the next cycle can retry.

    Args:
        pipeline_service: Service that executes the official pipeline.
        context: Short label included in log messages (e.g. ``"bootstrap"``).
        options: Optional run options passed through to the pipeline.
    """
    try:
        LOGGER.info("Starting %s pipeline run", context)
        result = await pipeline_service.run_pipeline(options)
        LOGGER.info(
            "%s pipeline complete: %d new alert(s), %d record(s) fetched",
            context.capitalize(),
            result.new_alerts_count,
            result.records_fetched
        )
        if result.source_failures:
            LOGGER.warning(
                "Source failures during %s run: %s",
                context,
                result.source_failures
            )
    except Exception:
        LOGGER.exception(
            "%s pipeline failed; will retry on next scheduled cycle",
            context
        )


async def run_early_warning_wrapper(
    pipeline_service: EarlyWarningPipelineService,
    *,
    context: str = "scheduled early-warning",
) -> None:
    """Run early-warning discovery and log success, skip, or failure.

    Exceptions are caught and logged so scheduled/bootstrap callers are not
    interrupted; the next cycle can retry.

    Args:
        pipeline_service: Service that executes early-warning discovery.
        context: Short label included in log messages.
    """
    try:
        LOGGER.info("Starting %s pipeline run", context)
        result = await pipeline_service.run()
        if result.skipped_due_to_overlap:
            LOGGER.warning("Skipped %s run because another pipeline is active", context)
            return
        LOGGER.info(
            "%s pipeline complete: %d new incident(s), %d page(s) scraped, %d failure(s)",
            context.capitalize(),
            result.new_incidents,
            result.pages_scraped,
            len(result.failures),
        )
    except Exception:
        LOGGER.exception(
            "%s pipeline failed; will retry on next scheduled cycle",
            context,
        )
