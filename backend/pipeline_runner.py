import logging

from models.pipeline_options import PipelineRunOptions
from services.pipeline import PipelineService

LOGGER = logging.getLogger(__name__)

async def run_pipeline_wrapper(pipeline_service: PipelineService, *, context: str, options: PipelineRunOptions | None = None) -> None:
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
