import unittest

from models.pipeline_options import PipelineRunOptions
from services.pipeline_progress import PipelineProgressTracker


class PipelineProgressPredictionTests(unittest.TestCase):
    def test_progress_increases_through_fetch_and_record_stages(self) -> None:
        tracker = PipelineProgressTracker()
        run_id = tracker.start_run(
            PipelineRunOptions(sources=["uk", "france"], limit=2),
        )

        snapshot = tracker.get_snapshot()
        self.assertEqual(snapshot.status, "running")
        self.assertGreaterEqual(snapshot.percent, 1.0)

        tracker.append_event(
            run_id=run_id,
            stage="source",
            source="uk",
            message="Completed source processing",
        )
        after_source = tracker.get_snapshot()
        self.assertGreater(after_source.percent, snapshot.percent)
        self.assertEqual(after_source.sources_completed, 1)

        tracker.append_event(
            run_id=run_id,
            stage="fetch",
            message="Source fetch completed",
            details={"records_fetched": 2},
        )
        tracker.append_event(
            run_id=run_id,
            stage="record",
            source="uk",
            message="Processing scraped record",
            details={"record_index": 1},
        )
        tracker.append_event(
            run_id=run_id,
            stage="agent",
            source="uk",
            message="translate_values started",
        )
        mid_record = tracker.get_snapshot()
        self.assertGreater(mid_record.percent, after_source.percent)

        tracker.append_event(
            run_id=run_id,
            stage="record",
            source="uk",
            message="Record processed successfully",
            details={"record_index": 1},
        )
        after_record = tracker.get_snapshot()
        self.assertGreater(after_record.percent, mid_record.percent)
        self.assertEqual(after_record.records_processed, 1)

        tracker.complete_run(
            run_id=run_id,
            new_alerts_count=1,
            records_fetched=2,
            source_failures={},
        )
        completed = tracker.get_snapshot()
        self.assertEqual(completed.status, "completed")
        self.assertEqual(completed.percent, 100.0)


if __name__ == "__main__":
    unittest.main()
