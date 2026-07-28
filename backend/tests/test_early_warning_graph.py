import asyncio
import time
import unittest
from datetime import date

from models.discovery_candidate import CandidateDecision, DiscoveryCandidate
from models.early_warning_incident import SourceKind, TrustTier
from models.scraped_record import ScrapedRecallRecord
from models.search_candidate import SearchCandidate
from services.early_warning.graph import (
    EarlyWarningProcessingService,
    IncidentExtraction,
    TaxonomyResult,
    _resolve_source_profile,
    _sanitize_publication_date,
    _to_incident,
)


class EarlyWarningGraphTests(unittest.IsolatedAsyncioTestCase):
    def test_metadata_relevance_prompt_requires_food_related_alert(self) -> None:
        captured: dict[str, str] = {}
        candidate = DiscoveryCandidate.from_search(
            SearchCandidate(
                title="Battery charger recall",
                url="https://example.test/charger-recall",
                description="Return the charger immediately.",
                rank=1,
                query_id="test-query",
                query="food recall United Kingdom",
                country="GB",
                language="en",
            ),
            decision=CandidateDecision.BORDERLINE,
            confidence=0.5,
            reasons=["awaiting review"],
        )

        def json_chat(**kwargs):
            captured["system_prompt"] = kwargs["system_prompt"]
            return {"relevant": False, "reason": "not food-related"}

        relevance = EarlyWarningProcessingService(json_chat=json_chat).classify_borderline(
            candidate
        )

        self.assertFalse(relevance.relevant)
        self.assertIn("The alert itself\nmust be food-related", captured["system_prompt"])
        self.assertIn("every non-food product recall", captured["system_prompt"])

    async def test_record_inference_does_not_block_event_loop(self) -> None:
        record = ScrapedRecallRecord(
            source_name="example",
            payload={
                "source_url": "https://example.test/advice",
                "visible_text": "Generic advice",
            },
        )
        responses = iter(
            [
                {"record": record.payload},
                {"content_type": "irrelevant", "reason": "generic advice"},
            ]
        )

        def slow_json_chat(**_kwargs):
            time.sleep(0.05)
            return next(responses)

        service = EarlyWarningProcessingService(json_chat=slow_json_chat)
        processing = asyncio.create_task(service.process_record(record))
        heartbeat = asyncio.create_task(asyncio.sleep(0))

        await asyncio.sleep(0.01)

        self.assertTrue(heartbeat.done())
        self.assertFalse(processing.done())
        self.assertIsNone(await processing)

    async def test_structures_incident_and_protects_source_provenance(self) -> None:
        record = ScrapedRecallRecord(
            source_name="news.example",
            payload={
                "source_url": "https://news.example/story",
                "canonical_url": "https://news.example/story",
                "title": "Cheese withdrawn",
                "visible_text": "Cheese was withdrawn because of possible Listeria.",
                "publication_date": "2026-07-20",
                "content_hash": "abc",
                "redirected_url_aliases": ["https://news.example/old"],
            },
        )
        responses = iter(
            [
                {"record": record.payload},
                {"content_type": "company_withdrawal", "reason": "explicit withdrawal"},
                {
                    "product_name": "Sample cheese",
                    "company_name": "Sample Foods",
                    "product_category": "Dairy",
                    "hazard_type": "Listeria",
                    "incident_reason": "Possible contamination",
                    "consumer_guidance": "Do not consume.",
                    "country": "Canada",
                    "affected_regions": ["Ontario"],
                    "publication_date": "2026-07-20",
                    "publisher": "Example News",
                    "source_kind": "major_news",
                    "original_language": "en",
                    "extraction_completeness": 0.9,
                },
            ]
        )
        service = EarlyWarningProcessingService(
            json_chat=lambda **_kwargs: next(responses),
            text_chat=lambda **_kwargs: "The company reports a precautionary withdrawal.",
        )

        incident = await service.process_record(
            record,
            source_kind=SourceKind.UNKNOWN,
            trust_tier=TrustTier.UNKNOWN,
        )

        assert incident is not None
        self.assertEqual(incident.incident_type, "company_withdrawal")
        self.assertEqual(incident.primary_source_url, record.payload["canonical_url"])
        self.assertEqual(incident.evidence[0].content_hash, "abc")
        self.assertEqual(incident.source_kind, SourceKind.MAJOR_NEWS)
        self.assertEqual(incident.trust_tier, TrustTier.MEDIUM)
        self.assertEqual(incident.evidence[0].source_kind, SourceKind.MAJOR_NEWS)

    async def test_configured_source_profile_overrides_extraction(self) -> None:
        record = ScrapedRecallRecord(
            source_name="authority.example",
            payload={
                "source_url": "https://authority.example/recall",
                "canonical_url": "https://authority.example/recall",
                "publication_date": "2026-07-20",
                "content_hash": "abc",
            },
        )
        responses = iter(
            [
                {"record": record.payload},
                {"content_type": "official_recall", "reason": "authority notice"},
                {
                    "product_name": "Yogurt",
                    "publisher": "Authority",
                    "source_kind": "major_news",
                    "extraction_completeness": 0.8,
                },
            ]
        )
        service = EarlyWarningProcessingService(
            json_chat=lambda **_kwargs: next(responses),
            text_chat=lambda **_kwargs: "An official recall was issued.",
        )

        incident = await service.process_record(
            record,
            source_kind=SourceKind.OFFICIAL_RECALL,
            trust_tier=TrustTier.OFFICIAL,
        )

        assert incident is not None
        self.assertEqual(incident.source_kind, SourceKind.OFFICIAL_RECALL)
        self.assertEqual(incident.trust_tier, TrustTier.OFFICIAL)

    async def test_irrelevant_page_is_not_converted(self) -> None:
        record = ScrapedRecallRecord(
            source_name="example",
            payload={
                "source_url": "https://example.test/advice",
                "visible_text": "Generic advice",
            },
        )
        responses = iter(
            [
                {"record": record.payload},
                {"content_type": "irrelevant", "reason": "generic advice"},
            ]
        )
        service = EarlyWarningProcessingService(
            json_chat=lambda **_kwargs: next(responses),
        )
        self.assertIsNone(await service.process_record(record))

    async def test_recall_listing_with_many_products_is_not_converted(self) -> None:
        record = ScrapedRecallRecord(
            source_name="example",
            payload={
                "source_url": "https://example.test/recalls",
                "canonical_url": "https://example.test/recalls",
                "visible_text": "Current recall listing",
            },
        )
        responses = iter(
            [
                {"record": record.payload},
                {"content_type": "official_recall", "reason": "recall listing"},
                {
                    "product_name": "Cheese, yogurt, ham, cereal, juice",
                    "country": "United Kingdom",
                    "publisher": "Example Authority",
                    "source_kind": "official_recall",
                },
            ]
        )
        service = EarlyWarningProcessingService(
            json_chat=lambda **_kwargs: next(responses),
            text_chat=lambda **_kwargs: "Several unrelated products are listed.",
        )

        self.assertIsNone(await service.process_record(record))

    async def test_electronics_recall_is_not_converted_after_extraction(self) -> None:
        record = ScrapedRecallRecord(
            source_name="example",
            payload={
                "source_url": "https://example.test/device-recall",
                "canonical_url": "https://example.test/device-recall",
                "visible_text": "A battery charger recall was issued.",
            },
        )
        responses = iter(
            [
                {"record": record.payload},
                {"content_type": "official_recall", "reason": "recall notice"},
                {
                    "product_name": "USB Battery Charger",
                    "product_category": "Electronics",
                    "country": "United Kingdom",
                    "publisher": "Example Authority",
                    "source_kind": "official_recall",
                },
            ]
        )
        service = EarlyWarningProcessingService(
            json_chat=lambda **_kwargs: next(responses),
            text_chat=lambda **_kwargs: "A battery charger has been recalled.",
        )

        self.assertIsNone(await service.process_record(record))

    def test_future_publication_dates_are_discarded(self) -> None:
        self.assertIsNone(
            _sanitize_publication_date(date(2027, 12, 8), today=date(2026, 7, 23))
        )
        self.assertEqual(
            _sanitize_publication_date(date(2026, 7, 18), today=date(2026, 7, 23)),
            date(2026, 7, 18),
        )

        record = ScrapedRecallRecord(
            source_name="news.example",
            payload={
                "source_url": "https://news.example/story",
                "canonical_url": "https://news.example/story",
                "publication_date": "2026-07-18",
                "content_hash": "abc",
            },
        )
        incident = _to_incident(
            record,
            taxonomy=TaxonomyResult(content_type="potential_recall", reason="test"),
            extraction=IncidentExtraction(
                product_name="Ice cream",
                publication_date=date(2027, 12, 8),
                publisher="Example News",
                source_kind=SourceKind.MAJOR_NEWS,
            ),
            summary="A recall was reported.",
            source_kind=SourceKind.MAJOR_NEWS,
            trust_tier=TrustTier.MEDIUM,
        )
        self.assertEqual(incident.publication_date, date(2026, 7, 18))

    def test_resolve_source_profile_prefers_extraction_when_unconfigured(self) -> None:
        kind, trust = _resolve_source_profile(
            configured_kind=SourceKind.UNKNOWN,
            configured_trust=TrustTier.UNKNOWN,
            extracted_kind=SourceKind.TRADE_PUBLICATION,
        )
        self.assertEqual(kind, SourceKind.TRADE_PUBLICATION)
        self.assertEqual(trust, TrustTier.MEDIUM)

    def test_invalid_extracted_source_kind_becomes_unknown(self) -> None:
        extraction = IncidentExtraction.model_validate({"source_kind": "news_outlet"})
        self.assertEqual(extraction.source_kind, SourceKind.UNKNOWN)

    def test_hazard_type_list_is_coerced_to_string(self) -> None:
        extraction = IncidentExtraction.model_validate(
            {
                "hazard_type": ["Salmonella presence", "manufacturing issues"],
                "product_name": ["Ice cream"],
            }
        )
        self.assertEqual(
            extraction.hazard_type,
            "Salmonella presence; manufacturing issues",
        )
        self.assertEqual(extraction.product_name, "Ice cream")

    async def test_taxonomy_retries_after_invalid_payload(self) -> None:
        record = ScrapedRecallRecord(
            source_name="news.example",
            payload={
                "source_url": "https://news.example/story",
                "canonical_url": "https://news.example/story",
                "visible_text": "A recall was issued.",
                "content_hash": "abc",
            },
        )
        responses = iter(
            [
                {"record": record.payload},
                {"content_type": "text/html", "reason": "wrong shape"},
                {"content_type": "potential_recall", "reason": "current recall"},
                {
                    "product_name": "Yogurt",
                    "hazard_type": ["Listeria"],
                    "source_kind": "major_news",
                    "extraction_completeness": 0.7,
                },
            ]
        )
        service = EarlyWarningProcessingService(
            json_chat=lambda **_kwargs: next(responses),
            text_chat=lambda **_kwargs: "A yogurt recall was reported.",
        )

        incident = await service.process_record(record)

        assert incident is not None
        self.assertEqual(incident.incident_type, "potential_recall")
        self.assertEqual(incident.hazard_type, "Listeria")

    def test_taxonomy_rejects_mime_content_type(self) -> None:
        with self.assertRaises(ValueError):
            TaxonomyResult.model_validate({"content_type": "text/html", "reason": "x"})


if __name__ == "__main__":
    unittest.main()
