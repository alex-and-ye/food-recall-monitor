import unittest
import asyncio
from datetime import date

from config.early_warning import load_early_warning_config
from db.chroma_early_warning_candidates import InMemoryEarlyWarningCandidateStore
from db.chroma_early_warning_client import InMemoryEarlyWarningIncidentStore
from db.chroma_warnings_client import InMemoryPipelineWarningsStore
from models.early_warning_incident import EarlyWarningIncidentCreate, IncidentType, SourceKind
from models.scraped_record import ScrapedRecallRecord
from models.search_candidate import SearchCandidate, SearchResponse
from services.early_warning.incidents import EarlyWarningIncidentService
from services.early_warning.pipeline import EarlyWarningPipelineService
from services.warnings import WarningsService


class FakeSearchClient:
    async def search(self, query, **_kwargs):
        return SearchResponse(
            query=query,
            candidates=[
                SearchCandidate(
                    title="Food recall warning",
                    url="https://inspection.canada.ca/recall/1",
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
            country="Canada",
            publication_date=date(2026, 7, 20),
            primary_source_url=record.payload["source_url"],
            source_kind=SourceKind.OFFICIAL_RECALL,
        )

    def classify_borderline(self, _candidate):
        raise AssertionError("accepted candidate should not need LLM metadata review")


class EarlyWarningPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_overlapping_run_is_skipped(self) -> None:
        config = load_early_warning_config().model_copy(update={"enabled": True})
        lock = asyncio.Lock()
        await lock.acquire()
        service = EarlyWarningPipelineService(
            config=config,
            search_client=FakeSearchClient(),  # type: ignore[arg-type]
            candidate_store=InMemoryEarlyWarningCandidateStore(),
            incident_service=EarlyWarningIncidentService(
                InMemoryEarlyWarningIncidentStore()
            ),
            processing_service=FakeProcessor(),  # type: ignore[arg-type]
            run_lock=lock,
        )
        try:
            result = await service.run()
        finally:
            lock.release()

        self.assertTrue(result.skipped_due_to_overlap)

    async def test_run_is_incremental_and_idempotent(self) -> None:
        config = load_early_warning_config()
        config = config.model_copy(
            update={
                "enabled": True,
                "budgets": config.budgets.model_copy(
                    update={
                        "queries_per_run": 1,
                        "results_per_query": 1,
                        "candidates_per_run": 1,
                    }
                ),
                "crawl": config.crawl.model_copy(
                    update={"concurrency": 1, "minimum_text_characters": 1}
                ),
            }
        )
        incident_store = InMemoryEarlyWarningIncidentStore()

        async def ingest(url, **_kwargs):
            return ScrapedRecallRecord(
                source_name="inspection.canada.ca",
                payload={
                    "source_url": url,
                    "canonical_url": url,
                    "visible_text": "Recall details",
                    "content_hash": "hash",
                },
            )

        service = EarlyWarningPipelineService(
            config=config,
            search_client=FakeSearchClient(),  # type: ignore[arg-type]
            candidate_store=InMemoryEarlyWarningCandidateStore(),
            incident_service=EarlyWarningIncidentService(incident_store),
            processing_service=FakeProcessor(),  # type: ignore[arg-type]
            ingest=ingest,
        )

        first = await service.run()
        second = await service.run()

        self.assertEqual(first.new_incidents, 1)
        self.assertEqual(second.new_incidents, 0)
        self.assertEqual(incident_store.count_incidents(), 1)
        self.assertEqual(first.pages_scraped, 1)

    async def test_dry_run_searches_without_scraping_or_persisting(self) -> None:
        config = load_early_warning_config()
        config = config.model_copy(
            update={
                "enabled": True,
                "budgets": config.budgets.model_copy(
                    update={
                        "queries_per_run": 1,
                        "results_per_query": 1,
                        "candidates_per_run": 1,
                    }
                ),
            }
        )
        incident_store = InMemoryEarlyWarningIncidentStore()
        scrape_calls = 0

        async def ingest(_url, **_kwargs):
            nonlocal scrape_calls
            scrape_calls += 1
            raise AssertionError("dry-run must not scrape pages")

        service = EarlyWarningPipelineService(
            config=config,
            search_client=FakeSearchClient(),  # type: ignore[arg-type]
            candidate_store=InMemoryEarlyWarningCandidateStore(),
            incident_service=EarlyWarningIncidentService(incident_store),
            processing_service=FakeProcessor(),  # type: ignore[arg-type]
            ingest=ingest,
        )

        result = await service.run(dry_run=True)

        self.assertTrue(result.dry_run)
        self.assertGreaterEqual(result.search_results, 1)
        self.assertEqual(result.pages_scraped, 0)
        self.assertEqual(result.incidents_saved, 0)
        self.assertEqual(scrape_calls, 0)
        self.assertEqual(incident_store.count_incidents(), 0)


class EarlyWarningPipelineWarningTests(unittest.IsolatedAsyncioTestCase):
    def _enabled_config(self):
        config = load_early_warning_config()
        return config.model_copy(
            update={
                "enabled": True,
                "budgets": config.budgets.model_copy(
                    update={
                        "queries_per_run": 1,
                        "results_per_query": 1,
                        "candidates_per_run": 1,
                        "max_pages_per_query": 1,
                    }
                ),
                "crawl": config.crawl.model_copy(
                    update={"concurrency": 1, "minimum_text_characters": 1, "max_attempts": 1}
                ),
            }
        )

    async def test_missing_search_client_emits_pipeline_failed_warning(self) -> None:
        warnings_service = WarningsService(InMemoryPipelineWarningsStore())
        service = EarlyWarningPipelineService(
            config=self._enabled_config(),
            search_client=None,
            candidate_store=InMemoryEarlyWarningCandidateStore(),
            incident_service=EarlyWarningIncidentService(
                InMemoryEarlyWarningIncidentStore()
            ),
            processing_service=FakeProcessor(),  # type: ignore[arg-type]
            warnings_service=warnings_service,
        )

        with self.assertRaisesRegex(RuntimeError, "Brave Search is unavailable"):
            await service.run()

        warnings = warnings_service.list_warnings()
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].category, "early_warning_pipeline_failed")
        self.assertIn("Brave Search is unavailable", warnings[0].message)

    async def test_search_failure_emits_search_warning(self) -> None:
        class FailingSearchClient:
            async def search(self, query, **_kwargs):
                raise RuntimeError("brave rate limited")

        warnings_service = WarningsService(InMemoryPipelineWarningsStore())
        service = EarlyWarningPipelineService(
            config=self._enabled_config(),
            search_client=FailingSearchClient(),  # type: ignore[arg-type]
            candidate_store=InMemoryEarlyWarningCandidateStore(),
            incident_service=EarlyWarningIncidentService(
                InMemoryEarlyWarningIncidentStore()
            ),
            processing_service=FakeProcessor(),  # type: ignore[arg-type]
            warnings_service=warnings_service,
        )

        result = await service.run(dry_run=True)

        self.assertEqual(result.search_results, 0)
        warnings = warnings_service.list_warnings()
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].category, "early_warning_search_failed")
        self.assertIn("brave rate limited", warnings[0].message)

    async def test_fetch_failure_emits_fetch_warning(self) -> None:
        warnings_service = WarningsService(InMemoryPipelineWarningsStore())

        async def ingest(_url, **_kwargs):
            raise RuntimeError("timeout fetching page")

        service = EarlyWarningPipelineService(
            config=self._enabled_config(),
            search_client=FakeSearchClient(),  # type: ignore[arg-type]
            candidate_store=InMemoryEarlyWarningCandidateStore(),
            incident_service=EarlyWarningIncidentService(
                InMemoryEarlyWarningIncidentStore()
            ),
            processing_service=FakeProcessor(),  # type: ignore[arg-type]
            warnings_service=warnings_service,
            ingest=ingest,
        )

        result = await service.run()

        self.assertEqual(result.pages_scraped, 0)
        warnings = warnings_service.list_warnings()
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].category, "early_warning_fetch_failed")
        self.assertIn("timeout fetching page", warnings[0].message)
        self.assertEqual(warnings[0].source, "inspection.canada.ca")

    async def test_processing_failure_emits_record_warning(self) -> None:
        class FailingProcessor(FakeProcessor):
            async def process_record(self, record, **_kwargs):
                raise RuntimeError("llm taxonomy failed")

        warnings_service = WarningsService(InMemoryPipelineWarningsStore())

        async def ingest(url, **_kwargs):
            return ScrapedRecallRecord(
                source_name="inspection.canada.ca",
                payload={
                    "source_url": url,
                    "canonical_url": url,
                    "visible_text": "Recall details",
                    "content_hash": "hash",
                },
            )

        service = EarlyWarningPipelineService(
            config=self._enabled_config(),
            search_client=FakeSearchClient(),  # type: ignore[arg-type]
            candidate_store=InMemoryEarlyWarningCandidateStore(),
            incident_service=EarlyWarningIncidentService(
                InMemoryEarlyWarningIncidentStore()
            ),
            processing_service=FailingProcessor(),  # type: ignore[arg-type]
            warnings_service=warnings_service,
            ingest=ingest,
        )

        result = await service.run()

        self.assertEqual(result.incidents_saved, 0)
        warnings = warnings_service.list_warnings()
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].category, "early_warning_record_skipped")
        self.assertIn("llm taxonomy failed", warnings[0].message)


if __name__ == "__main__":
    unittest.main()
