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
from services.early_warning.graph import BorderlineRelevance
from services.early_warning.incidents import EarlyWarningIncidentService
from services.early_warning.pipeline import (
    EarlyWarningPipelineService,
    _listing_detail_links,
    _place_matches_alias,
)
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
    def __init__(self) -> None:
        self.metadata_reviews = 0

    async def process_record(self, record, **_kwargs):
        return EarlyWarningIncidentCreate(
            incident_type=IncidentType.POTENTIAL_RECALL,
            product_name="Sample cheese",
            hazard_type="Listeria",
            summary="A possible contamination prompted a warning.",
            country="United Kingdom",
            publication_date=date(2026, 7, 20),
            primary_source_url=record.payload["source_url"],
            source_kind=SourceKind.OFFICIAL_RECALL,
        )

    def classify_borderline(self, _candidate):
        self.metadata_reviews += 1
        return BorderlineRelevance(relevant=True, reason="food recall metadata")

class EarlyWarningPipelineTests(unittest.IsolatedAsyncioTestCase):
    def test_target_country_matching_is_explicit(self) -> None:
        self.assertTrue(_place_matches_alias("England", "England"))
        self.assertTrue(_place_matches_alias("Nationwide, United Kingdom", "United Kingdom"))
        self.assertFalse(_place_matches_alias("Canada", "France"))
        self.assertFalse(_place_matches_alias("European Union", "Germany"))

    def test_listing_page_requires_multiple_recall_detail_links(self) -> None:
        record = ScrapedRecallRecord(
            source_name="authority.example",
            payload={
                "canonical_url": "https://authority.example/recalls",
                "title": "Latest food recalls",
                "detail_links": [
                    {"url": f"https://authority.example/recall/{index}", "title": f"Recall {index}"}
                    for index in range(3)
                ],
            },
        )
        self.assertEqual(len(_listing_detail_links(record)), 3)

    async def test_out_of_scope_incident_is_not_persisted(self) -> None:
        class OutsideProcessor(FakeProcessor):
            async def process_record(self, record, **_kwargs):
                incident = await super().process_record(record, **_kwargs)
                return incident.model_copy(update={"country": "Canada"})

        config = load_early_warning_config().model_copy(update={"enabled": True})
        store = InMemoryEarlyWarningIncidentStore()

        async def ingest(url, **_kwargs):
            return ScrapedRecallRecord(
                source_name="news.example",
                payload={
                    "source_url": url,
                    "canonical_url": url,
                    "visible_text": "Recall details",
                    "content_hash": "outside-country",
                },
            )

        service = EarlyWarningPipelineService(
            config=config,
            search_client=FakeSearchClient(),  # type: ignore[arg-type]
            candidate_store=InMemoryEarlyWarningCandidateStore(),
            incident_service=EarlyWarningIncidentService(store),
            processing_service=OutsideProcessor(),  # type: ignore[arg-type]
            ingest=ingest,
        )

        result = await service.run()

        self.assertEqual(result.incidents_saved, 0)
        self.assertEqual(store.count_incidents(), 0)

    async def test_overlapping_run_waits_for_lock(self) -> None:
        config = load_early_warning_config().model_copy(update={"enabled": True})
        lock = asyncio.Lock()
        await lock.acquire()
        started = asyncio.Event()
        finished = asyncio.Event()

        class RecordingProcessor(FakeProcessor):
            async def process_record(self, record, **kwargs):
                started.set()
                return await super().process_record(record, **kwargs)

        async def ingest(url, **_kwargs):
            return ScrapedRecallRecord(
                source_name="news.example",
                payload={
                    "source_url": url,
                    "canonical_url": url,
                    "visible_text": "Recall details",
                    "content_hash": "wait-for-lock",
                },
            )

        service = EarlyWarningPipelineService(
            config=config,
            search_client=FakeSearchClient(),  # type: ignore[arg-type]
            candidate_store=InMemoryEarlyWarningCandidateStore(),
            incident_service=EarlyWarningIncidentService(
                InMemoryEarlyWarningIncidentStore()
            ),
            processing_service=RecordingProcessor(),  # type: ignore[arg-type]
            ingest=ingest,
            run_lock=lock,
        )

        async def run_and_mark() -> None:
            await service.run()
            finished.set()

        task = asyncio.create_task(run_and_mark())
        try:
            await asyncio.sleep(0)
            self.assertFalse(started.is_set())
            self.assertFalse(finished.is_set())
            lock.release()
            await asyncio.wait_for(finished.wait(), timeout=5)
            self.assertTrue(started.is_set())
        finally:
            if lock.locked():
                lock.release()
            await task

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

        processor = FakeProcessor()
        service = EarlyWarningPipelineService(
            config=config,
            search_client=FakeSearchClient(),  # type: ignore[arg-type]
            candidate_store=InMemoryEarlyWarningCandidateStore(),
            incident_service=EarlyWarningIncidentService(incident_store),
            processing_service=processor,  # type: ignore[arg-type]
            ingest=ingest,
        )

        first = await service.run()
        second = await service.run()

        self.assertEqual(first.new_incidents, 1)
        self.assertEqual(second.new_incidents, 0)
        self.assertEqual(incident_store.count_incidents(), 1)
        self.assertEqual(first.pages_scraped, 1)
        self.assertGreaterEqual(processor.metadata_reviews, 1)

    async def test_llm_rejection_prevents_non_food_result_from_being_scraped(self) -> None:
        class NonFoodProcessor(FakeProcessor):
            def classify_borderline(self, _candidate):
                self.metadata_reviews += 1
                return BorderlineRelevance(
                    relevant=False,
                    reason="battery charger recall is not food-related",
                )

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
        processor = NonFoodProcessor()
        scrape_calls = 0

        async def ingest(_url, **_kwargs):
            nonlocal scrape_calls
            scrape_calls += 1
            raise AssertionError("a rejected search result must not be scraped")

        service = EarlyWarningPipelineService(
            config=config,
            search_client=FakeSearchClient(),  # type: ignore[arg-type]
            candidate_store=InMemoryEarlyWarningCandidateStore(),
            incident_service=EarlyWarningIncidentService(
                InMemoryEarlyWarningIncidentStore()
            ),
            processing_service=processor,  # type: ignore[arg-type]
            ingest=ingest,
        )

        result = await service.run()

        self.assertEqual(processor.metadata_reviews, 1)
        self.assertEqual(scrape_calls, 0)
        self.assertEqual(result.candidates_rejected, 1)
        self.assertEqual(result.pages_scraped, 0)

    async def test_run_notifies_broadcaster_after_each_saved_incident(self) -> None:
        from unittest.mock import Mock

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
        broadcaster = Mock()

        async def ingest(url, **_kwargs):
            return ScrapedRecallRecord(
                source_name="inspection.canada.ca",
                payload={
                    "source_url": url,
                    "canonical_url": url,
                    "visible_text": "Recall details",
                    "content_hash": "hash-notify",
                },
            )

        service = EarlyWarningPipelineService(
            config=config,
            search_client=FakeSearchClient(),  # type: ignore[arg-type]
            candidate_store=InMemoryEarlyWarningCandidateStore(),
            incident_service=EarlyWarningIncidentService(
                InMemoryEarlyWarningIncidentStore()
            ),
            processing_service=FakeProcessor(),  # type: ignore[arg-type]
            broadcaster=broadcaster,
            ingest=ingest,
        )

        result = await service.run()
        dry = await service.run(dry_run=True)

        self.assertEqual(result.incidents_saved, 1)
        self.assertEqual(dry.incidents_saved, 0)
        broadcaster.notify.assert_called_once_with(1)

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
