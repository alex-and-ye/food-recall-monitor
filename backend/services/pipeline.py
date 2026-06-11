from agents.graph import run_pipeline as run_agent_pipeline
from db.interface import FoodRecallAlertsDBInterface
from models.pipeline_options import PipelineRunOptions
from models.pipeline_result import PipelineRunResult

class PipelineService:
    def __init__(self, db: FoodRecallAlertsDBInterface) -> None:
        self.db = db

    async def run_pipeline(self, options: PipelineRunOptions | None = None) -> PipelineRunResult:
        run_options = options or PipelineRunOptions()
        pipeline_result = await run_agent_pipeline(run_options)
        saved_count = self.db.save_alerts(pipeline_result.alerts)
        return PipelineRunResult(
            new_alerts_count=saved_count,
            records_fetched=pipeline_result.records_fetched,
            source_failures=pipeline_result.source_failures,
        )
