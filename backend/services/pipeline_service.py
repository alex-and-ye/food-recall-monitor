from agents.graph import run_pipeline as run_agent_pipeline
from db.interface import FoodRecallAlertsDBInterface
from models.pipeline_options import PipelineRunOptions

class PipelineService:
    def __init__(self, db: FoodRecallAlertsDBInterface) -> None:
        self.db = db

    async def run_pipeline(self, options: PipelineRunOptions | None = None) -> int:
        run_options = options or PipelineRunOptions()
        extracted_alerts = await run_agent_pipeline(run_options)
        return self.db.save_alerts(extracted_alerts)
