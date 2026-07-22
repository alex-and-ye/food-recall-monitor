from __future__ import annotations

import unittest
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

from db.chroma_pipeline_logs_client import InMemoryPipelineRunLogsStore
from models.pipeline_options import PipelineRunOptions
from models.pipeline_progress import PipelineStage
from models.pipeline_run_log import (
    MAX_PIPELINE_LOG_EVENTS_RETAINED,
    PipelineKind,
    PipelineRunLogEvent,
)
from services.pipeline_progress import PipelineProgressTracker


class InMemoryPipelineRunLogsStoreTests(unittest.TestCase):
    def test_append_and_list_by_run_and_kind(self) -> None:
        store = InMemoryPipelineRunLogsStore()
        official = PipelineRunLogEvent(
            event_id="e1",
            run_id="run-official",
            pipeline_kind=PipelineKind.OFFICIAL,
            created_at=datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc),
            stage=PipelineStage.PIPELINE,
            message="Pipeline run started",
        )
        early = PipelineRunLogEvent(
            event_id="e2",
            run_id="run-ew",
            pipeline_kind=PipelineKind.EARLY_WARNING,
            created_at=datetime(2026, 7, 22, 12, 1, tzinfo=timezone.utc),
            stage=PipelineStage.EARLY_WARNING,
            message="Early-warning pipeline run started",
        )
        store.append(official)
        store.append(early)

        self.assertEqual(store.count_events(), 2)
        self.assertEqual(
            [event.event_id for event in store.list_events(run_id="run-ew")],
            ["e2"],
        )
        self.assertEqual(
            store.list_run_ids(pipeline_kind=PipelineKind.OFFICIAL),
            ["run-official"],
        )

    def test_prunes_oldest_events(self) -> None:
        store = InMemoryPipelineRunLogsStore()
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for index in range(MAX_PIPELINE_LOG_EVENTS_RETAINED + 3):
            store.append(
                PipelineRunLogEvent(
                    event_id=f"event-{index}",
                    run_id="run",
                    pipeline_kind=PipelineKind.OFFICIAL,
                    created_at=base.replace(microsecond=index),
                    stage=PipelineStage.PIPELINE,
                    message=f"event {index}",
                )
            )
        self.assertEqual(store.count_events(), MAX_PIPELINE_LOG_EVENTS_RETAINED)
        event_ids = {event.event_id for event in store.list_events()}
        self.assertNotIn("event-0", event_ids)
        self.assertNotIn("event-1", event_ids)
        self.assertNotIn("event-2", event_ids)


class PipelineProgressTrackerDbTests(unittest.TestCase):
    def test_official_run_persists_start_and_complete_events(self) -> None:
        store = InMemoryPipelineRunLogsStore()
        tracker = PipelineProgressTracker(store)

        run_id = tracker.start_run(
            PipelineRunOptions(),
            pipeline_kind=PipelineKind.OFFICIAL,
        )
        tracker.reporter(run_id).log(
            stage=PipelineStage.CRAWL,
            message="Starting source crawl",
            source="uk",
        )
        tracker.complete_run(run_id=run_id, new_alerts_count=2, records_fetched=5)

        events = store.list_events(run_id=run_id)
        messages = [event.message for event in reversed(events)]
        self.assertEqual(messages[0], "Pipeline run started")
        self.assertIn("Starting source crawl", messages)
        self.assertEqual(messages[-1], "Pipeline run completed")
        self.assertTrue(all(event.pipeline_kind == PipelineKind.OFFICIAL for event in events))
        self.assertEqual(events[0].details.get("new_alerts_count"), 2)

    def test_early_warning_run_persists_failure(self) -> None:
        store = InMemoryPipelineRunLogsStore()
        tracker = PipelineProgressTracker(store)

        run_id = tracker.start_run(pipeline_kind=PipelineKind.EARLY_WARNING)
        tracker.fail_run(run_id=run_id, error="brave unavailable")

        events = list(reversed(store.list_events(run_id=run_id)))
        self.assertEqual(events[0].message, "Early-warning pipeline run started")
        self.assertEqual(events[-1].message, "Early-warning pipeline run failed")
        self.assertEqual(events[-1].details.get("error"), "brave unavailable")
        self.assertTrue(
            all(event.pipeline_kind == PipelineKind.EARLY_WARNING for event in events)
        )


class EarlyWarningPipelineLoggingTests(unittest.IsolatedAsyncioTestCase):
    async def test_dry_run_writes_db_logs(self) -> None:
        from config.early_warning import load_early_warning_config
        from db.chroma_early_warning_candidates import InMemoryEarlyWarningCandidateStore
        from db.chroma_early_warning_client import InMemoryEarlyWarningIncidentStore
        from models.early_warning_incident import EarlyWarningIncidentCreate, IncidentType, SourceKind
        from models.search_candidate import SearchCandidate, SearchResponse
        from services.early_warning.incidents import EarlyWarningIncidentService
        from services.early_warning.pipeline import EarlyWarningPipelineService

        class FakeSearchClient:
            async def search(self, query, **_kwargs):
                return SearchResponse(
                    query=query,
                    candidates=[
                        SearchCandidate(
                            title="Food recall warning",
                            url="https://example.com/recall/1",
                            description="Food contamination notice",
                            rank=1,
                            query_id=query.query_id,
                            query=query.text,
                            country=query.country,
                            language=query.language,
                        )
                    ],
                )

        class FakeProcessor:
            async def process_record(self, record, **_kwargs):
                return EarlyWarningIncidentCreate(
                    incident_type=IncidentType.POTENTIAL_RECALL,
                    product_name="Sample cheese",
                    hazard_type="Listeria",
                    summary="A possible contamination prompted a warning.",
                    country="United States",
                    publication_date=date(2026, 7, 20),
                    primary_source_url=record.payload["source_url"],
                    source_kind=SourceKind.NEWS_OUTLET,
                )

            def classify_borderline(self, _candidate):
                raise AssertionError("accepted candidate should not need LLM metadata review")

        config = load_early_warning_config().model_copy(
            update={
                "enabled": True,
                "budgets": load_early_warning_config().budgets.model_copy(
                    update={
                        "queries_per_run": 1,
                        "results_per_query": 1,
                        "candidates_per_run": 1,
                    }
                ),
            }
        )
        store = InMemoryPipelineRunLogsStore()
        tracker = PipelineProgressTracker(store)
        service = EarlyWarningPipelineService(
            config=config,
            search_client=FakeSearchClient(),  # type: ignore[arg-type]
            candidate_store=InMemoryEarlyWarningCandidateStore(),
            incident_service=EarlyWarningIncidentService(
                InMemoryEarlyWarningIncidentStore()
            ),
            processing_service=FakeProcessor(),  # type: ignore[arg-type]
            progress_tracker=tracker,
            ingest=AsyncMock(side_effect=AssertionError("dry-run must not scrape")),
        )

        result = await service.run(dry_run=True)

        self.assertTrue(result.dry_run)
        events = list(reversed(store.list_events()))
        self.assertGreaterEqual(len(events), 3)
        self.assertEqual(events[0].message, "Early-warning pipeline run started")
        self.assertEqual(events[0].pipeline_kind, PipelineKind.EARLY_WARNING)
        self.assertTrue(
            any(event.message == "Starting early-warning discovery" for event in events)
        )
        self.assertEqual(events[-1].message, "Early-warning pipeline run completed")


if __name__ == "__main__":
    unittest.main()
