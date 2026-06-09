from db.interface import FoodRecallAlertsDBInterface
from models.pipeline_options import PipelineRunOptions

class PipelineService:
    def __init__(self, db: FoodRecallAlertsDBInterface) -> None:
        self.db = db

    async def run_pipeline(self, options: PipelineRunOptions | None = None) -> int:
        run_options = options or PipelineRunOptions()
        # TODO: Trigger AI Agents Pipeline here
        # The real implementation will fetch the selected sources, run the
        # agent graph, and pass FoodRecallAlertCreate models into the DB layer.
        _ = run_options
        return 0
