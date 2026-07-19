import unittest

from db.chroma_warnings_client import InMemoryPipelineWarningsStore
from models.pipeline_warning import MAX_WARNINGS_RETAINED, PipelineWarningCreate
from services.warnings import WarningsService


class InMemoryPipelineWarningsStoreTests(unittest.TestCase):
    def test_create_list_and_acknowledge(self) -> None:
        store = InMemoryPipelineWarningsStore()
        created = store.create(
            PipelineWarningCreate(
                category="source_skipped",
                message='Source "france" was skipped during scraping',
                source="france",
                run_id="run-1",
            )
        )

        self.assertFalse(created.acknowledged)
        self.assertEqual(store.count_unacknowledged(), 1)
        listed = store.list_warnings()
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0].warning_id, created.warning_id)

        acknowledged = store.acknowledge(created.warning_id)
        assert acknowledged is not None
        self.assertTrue(acknowledged.acknowledged)
        self.assertEqual(store.count_unacknowledged(), 0)
        self.assertEqual(store.list_warnings(acknowledged=False), [])
        self.assertEqual(len(store.list_warnings(acknowledged=True)), 1)

    def test_acknowledge_all(self) -> None:
        store = InMemoryPipelineWarningsStore()
        store.create(
            PipelineWarningCreate(category="record_skipped", message="Record skipped", source="uk")
        )
        store.create(
            PipelineWarningCreate(category="pipeline_failed", message="Pipeline failed")
        )

        updated = store.acknowledge_all()
        self.assertEqual(updated, 2)
        self.assertEqual(store.count_unacknowledged(), 0)
        self.assertEqual(store.acknowledge_all(), 0)

    def test_prune_keeps_newest_warnings(self) -> None:
        store = InMemoryPipelineWarningsStore()

        for index in range(MAX_WARNINGS_RETAINED + 5):
            store.create(
                PipelineWarningCreate(
                    category="source_skipped",
                    message=f"Warning {index}",
                    source="uk",
                )
            )

        warnings = store.list_warnings()
        self.assertEqual(len(warnings), MAX_WARNINGS_RETAINED)


class WarningsServiceTests(unittest.TestCase):
    def test_emit_truncates_long_message(self) -> None:
        store = InMemoryPipelineWarningsStore()
        service = WarningsService(store)
        long_message = "x" * 500

        warning = service.emit(category="pipeline_failed", message=long_message)

        self.assertLessEqual(len(warning.message), 280)
        self.assertTrue(warning.message.endswith("…"))
        self.assertEqual(service.get_summary().unacknowledged_count, 1)


if __name__ == "__main__":
    unittest.main()
