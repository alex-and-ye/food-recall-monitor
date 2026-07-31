import unittest
from types import SimpleNamespace
from unittest.mock import patch

from bootstrap import run_early_warning_bootstrap

class EarlyWarningBootstrapTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_incidents_db_starts_bootstrap_run(self) -> None:
        incident_service = SimpleNamespace(store=SimpleNamespace(count_incidents=lambda: 0))
        pipeline_service = SimpleNamespace()
        created: list[str] = []

        def fake_create_task(coro, *, name=None):
            created.append(name or "")
            coro.close()
            return SimpleNamespace()

        with patch("bootstrap.asyncio.create_task", side_effect=fake_create_task):
            await run_early_warning_bootstrap(incident_service, pipeline_service)  # type: ignore[arg-type]

        self.assertEqual(created, ["bootstrap-early-warning-run"])

    async def test_non_empty_incidents_db_does_not_bootstrap(self) -> None:
        incident_service = SimpleNamespace(store=SimpleNamespace(count_incidents=lambda: 3))
        pipeline_service = SimpleNamespace()

        with patch("bootstrap.asyncio.create_task") as create_task:
            await run_early_warning_bootstrap(incident_service, pipeline_service)  # type: ignore[arg-type]

        create_task.assert_not_called()

if __name__ == "__main__":
    unittest.main()
