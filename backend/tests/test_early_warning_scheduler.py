import unittest
from types import SimpleNamespace

from scheduler import (
    start_daily_pipeline_scheduler,
    start_early_warning_scheduler,
    stop_daily_pipeline_scheduler,
    stop_early_warning_scheduler,
)


class EarlyWarningSchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_mode_starts_no_job(self) -> None:
        service = SimpleNamespace(
            config=SimpleNamespace(
                enabled=False,
                scheduler=SimpleNamespace(interval_minutes=1, run_immediately=False),
            )
        )

        task, stop_event = start_early_warning_scheduler(service)  # type: ignore[arg-type]

        self.assertIsNone(task)
        self.assertIsNone(stop_event)
        await stop_early_warning_scheduler(task, stop_event)

    async def test_disabled_official_pipeline_starts_no_job(self) -> None:
        task, stop_event = start_daily_pipeline_scheduler(
            SimpleNamespace(),  # type: ignore[arg-type]
            enabled=False,
        )

        self.assertIsNone(task)
        self.assertIsNone(stop_event)
        await stop_daily_pipeline_scheduler(task, stop_event)


if __name__ == "__main__":
    unittest.main()
