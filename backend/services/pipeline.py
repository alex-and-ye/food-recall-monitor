from agents.graph import run_pipeline as run_agent_pipeline
from db.interface import FoodRecallAlertsDBInterface
from models.pipeline_options import PipelineRunOptions
from models.pipeline_result import PipelineRunResult
from services.alert_events import AlertChangeBroadcaster
from services.pipeline_progress import PipelineProgressTracker

class PipelineService:
    def __init__(
        self,
        db: FoodRecallAlertsDBInterface,
        progress_tracker: PipelineProgressTracker | None = None,
        alert_broadcaster: AlertChangeBroadcaster | None = None,
    ) -> None:
        self.db = db
        self.progress_tracker = progress_tracker
        self.alert_broadcaster = alert_broadcaster

    async def run_pipeline(
        self,
        options: PipelineRunOptions | None = None,
        *,
        run_id: str | None = None,
    ) -> PipelineRunResult:
        run_options = options or PipelineRunOptions()
        active_run_id = run_id
        reporter = None
        if self.progress_tracker is not None:
            if active_run_id is None:
                active_run_id = self.progress_tracker.start_run(run_options)
            reporter = self.progress_tracker.reporter(active_run_id)

        try:
            pipeline_result = await run_agent_pipeline(run_options, reporter=reporter)
            if reporter is not None:
                reporter.log(
                    stage="db",
                    message="Persisting alerts to database",
                    details={
                        "alerts_to_save": len(pipeline_result.alerts),
                        "alerts": [alert.model_dump(mode="json") for alert in pipeline_result.alerts],
                    },
                )
            saved_count = self.db.save_alerts(pipeline_result.alerts)
            if self.alert_broadcaster is not None:
                self.alert_broadcaster.notify(saved_count)
            if self.progress_tracker is not None and active_run_id is not None:
                self.progress_tracker.complete_run(
                    run_id=active_run_id,
                    new_alerts_count=saved_count,
                    records_fetched=pipeline_result.records_fetched,
                    source_failures=pipeline_result.source_failures,
                )
        except Exception as exc:
            if self.progress_tracker is not None and active_run_id is not None:
                self.progress_tracker.fail_run(run_id=active_run_id, error=str(exc))
            raise

        return PipelineRunResult(
            new_alerts_count=saved_count,
            records_fetched=pipeline_result.records_fetched,
            source_failures=pipeline_result.source_failures,
        )
