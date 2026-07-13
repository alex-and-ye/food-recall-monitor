from agents.graph import run_pipeline as run_agent_pipeline
from db.interface import FoodRecallAlertsDBInterface
from models.food_recall_alert import FoodRecallAlertCreate
from models.pipeline_options import PipelineRunOptions
from models.pipeline_result import PipelineRunResult
from services.alert_events import AlertChangeBroadcaster
from services.geocoding import geocode_alert_location
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

    async def run_pipeline(self, options: PipelineRunOptions | None = None) -> PipelineRunResult:
        run_options = options or PipelineRunOptions()
        run_id: str | None = None
        reporter = None
        if self.progress_tracker is not None:
            run_id = self.progress_tracker.start_run(run_options)
            reporter = self.progress_tracker.reporter(run_id)

        try:
            saved_count = 0

            async def save_alert_incrementally(alert: FoodRecallAlertCreate) -> int:
                nonlocal saved_count
                saved_alerts = self.db.save_alerts([alert])
                inserted_count = len(saved_alerts)
                saved_count += inserted_count

                for saved_alert in saved_alerts:
                    coordinates = await geocode_alert_location(alert)
                    self.db.update_alert_coordinates(
                        saved_alert.alert_id,
                        coordinates.latitude,
                        coordinates.longitude,
                    )

                if reporter is not None:
                    reporter.log(
                        stage="db",
                        message="Alert persisted to database",
                        details={
                            "saved_for_alert": inserted_count,
                            "saved_so_far": saved_count,
                            "alert": alert.model_dump(mode="json"),
                        },
                    )
                if self.alert_broadcaster is not None and inserted_count > 0:
                    self.alert_broadcaster.notify(inserted_count)
                return inserted_count

            pipeline_result = await run_agent_pipeline(
                run_options,
                reporter=reporter,
                on_alert_processed=save_alert_incrementally,
            )
            if self.progress_tracker is not None and run_id is not None:
                self.progress_tracker.complete_run(
                    run_id=run_id,
                    new_alerts_count=saved_count,
                    records_fetched=pipeline_result.records_fetched,
                    source_failures=pipeline_result.source_failures,
                )
        except Exception as exc:
            if self.progress_tracker is not None and run_id is not None:
                self.progress_tracker.fail_run(run_id=run_id, error=str(exc))
            raise

        return PipelineRunResult(
            new_alerts_count=saved_count,
            records_fetched=pipeline_result.records_fetched,
            source_failures=pipeline_result.source_failures,
        )
