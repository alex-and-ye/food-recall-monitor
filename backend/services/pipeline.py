"""Orchestrates the official food-recall scraping and persistence pipeline.

Runs the agent graph under an optional lock, persists alerts incrementally,
geocodes map pins, updates the semantic index, and verifies early-warning
incidents against newly saved official recalls.
"""

import asyncio

from agents.graph import run_pipeline as run_agent_pipeline
from agents.errors import SourceFetchError
from db.interface import FoodRecallAlertsDBInterface
from db.source_config_interface import ScraperSourceConfigDBInterface
from models.food_recall_alert import FoodRecallAlertCreate
from models.pipeline_options import PipelineRunOptions
from models.pipeline_progress import PipelineStage
from models.pipeline_result import PipelineRunResult
from models.pipeline_warning import WarningCategory
from services.alert_events import AlertChangeBroadcaster
from services.geocoding import geocode_alert_location
from models.pipeline_run_log import PipelineKind
from services.pipeline_progress import PipelineProgressTracker
from services.warnings import WarningsService
from services.early_warning.verification import IncidentVerificationService
from services.early_warning.semantic_index import SafetyEventSemanticIndex


class PipelineService:
    """Run the official recall pipeline and persist resulting alerts."""

    def __init__(
        self,
        db: FoodRecallAlertsDBInterface,
        source_db: ScraperSourceConfigDBInterface,
        progress_tracker: PipelineProgressTracker | None = None,
        alert_broadcaster: AlertChangeBroadcaster | None = None,
        warnings_service: WarningsService | None = None,
        verification_service: IncidentVerificationService | None = None,
        incident_broadcaster: AlertChangeBroadcaster | None = None,
        run_lock: asyncio.Lock | None = None,
        semantic_index: SafetyEventSemanticIndex | None = None,
    ) -> None:
        """Wire pipeline dependencies for persistence, progress, and side effects.

        Args:
            db: Alerts database for saving and updating coordinates.
            source_db: Scraper source configuration store.
            progress_tracker: Optional run progress / log tracker.
            alert_broadcaster: Optional broadcaster for new official alerts.
            warnings_service: Optional service for operational warnings.
            verification_service: Optional early-warning official verification.
            incident_broadcaster: Optional broadcaster for confirmed incidents.
            run_lock: Optional lock serializing heavy pipeline runs.
            semantic_index: Optional similarity index for saved alerts.
        """
        self.db = db
        self.source_db = source_db
        self.progress_tracker = progress_tracker
        self.alert_broadcaster = alert_broadcaster
        self.warnings_service = warnings_service
        self.verification_service = verification_service
        self.incident_broadcaster = incident_broadcaster
        self.run_lock = run_lock
        self.semantic_index = semantic_index

    async def run_pipeline(self, options: PipelineRunOptions | None = None) -> PipelineRunResult:
        """Run the pipeline, acquiring ``run_lock`` when configured.

        Args:
            options: Optional run options; defaults are used when omitted.

        Returns:
            Aggregate result with saved counts and source failure info.

        Raises:
            Exception: Propagates pipeline failures after marking the run failed.
        """
        if self.run_lock is None:
            return await self._run_pipeline(options)
        async with self.run_lock:
            return await self._run_pipeline(options)

    async def _run_pipeline(self, options: PipelineRunOptions | None = None) -> PipelineRunResult:
        """Execute one official pipeline run with incremental alert persistence.

        Args:
            options: Optional run options.

        Returns:
            PipelineRunResult summarizing the completed run.

        Raises:
            Exception: On hard pipeline failure after emitting warnings.
        """
        run_options = options or PipelineRunOptions()
        run_id: str | None = None
        reporter = None
        if self.progress_tracker is not None:
            run_id = self.progress_tracker.start_run(
                run_options,
                pipeline_kind=PipelineKind.OFFICIAL,
            )
            reporter = self.progress_tracker.reporter(run_id)

        try:
            saved_count = 0
            saved_alert_records = []

            async def save_alert_incrementally(alert: FoodRecallAlertCreate) -> int:
                """Persist one alert, geocode it, and notify subscribers.

                Args:
                    alert: Newly processed alert to save.

                Returns:
                    Number of alerts inserted for this payload.
                """
                nonlocal saved_count
                saved_alerts = self.db.save_alerts([alert])
                saved_alert_records.extend(saved_alerts)
                inserted_count = len(saved_alerts)
                saved_count += inserted_count

                for saved_alert in saved_alerts:
                    if self.semantic_index is not None:
                        try:
                            self.semantic_index.upsert_official_alert(saved_alert)
                        except Exception:
                            # Similarity is a derived index; official recall
                            # persistence must remain authoritative.
                            pass
                    coordinates = await geocode_alert_location(alert)
                    self.db.update_alert_coordinates(
                        saved_alert.alert_id,
                        coordinates.latitude,
                        coordinates.longitude,
                    )

                if reporter is not None:
                    reporter.log(
                        stage=PipelineStage.DB,
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
                source_db=self.source_db,
                reporter=reporter,
                on_alert_processed=save_alert_incrementally,
                on_warning=self._emit_warning,
                run_id=run_id,
            )
            if self.verification_service is not None and saved_alert_records:
                verification_results = self.verification_service.verify_unresolved(
                    saved_alert_records
                )
                confirmed_count = sum(result.confirmed for result in verification_results)
                if confirmed_count and self.incident_broadcaster is not None:
                    self.incident_broadcaster.notify(confirmed_count)
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
            self._emit_hard_failure(exc, run_id=run_id)
            raise

        return PipelineRunResult(
            new_alerts_count=saved_count,
            records_fetched=pipeline_result.records_fetched,
            source_failures=pipeline_result.source_failures,
        )

    def _emit_warning(
        self,
        *,
        category: WarningCategory | str,
        message: str,
        source: str | None = None,
        run_id: str | None = None,
    ) -> None:
        """Forward a soft pipeline warning when a warnings service is configured.

        Args:
            category: Warning category or convertible string value.
            message: Human-readable warning text.
            source: Optional source name.
            run_id: Optional pipeline run identifier.
        """
        if self.warnings_service is None:
            return
        self.warnings_service.emit(
            category=WarningCategory(category),
            message=message,
            source=source,
            run_id=run_id,
        )

    def _emit_hard_failure(self, exc: Exception, *, run_id: str | None) -> None:
        """Emit structured warnings for a hard pipeline failure.

        Args:
            exc: Exception that failed the run.
            run_id: Active run identifier, if any.
        """
        if self.warnings_service is None:
            return
        if isinstance(exc, SourceFetchError):
            for source_name, error in exc.failures.items():
                self.warnings_service.emit(
                    category=WarningCategory.SOURCE_SKIPPED,
                    message=f'Source "{source_name}" was skipped during scraping: {error}',
                    source=source_name,
                    run_id=run_id,
                )
            return
        self.warnings_service.emit(
            category=WarningCategory.PIPELINE_FAILED,
            message=f"Pipeline run failed: {exc}",
            run_id=run_id,
        )
