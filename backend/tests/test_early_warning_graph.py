import unittest

from models.early_warning_incident import SourceKind, TrustTier
from models.scraped_record import ScrapedRecallRecord
from services.early_warning.graph import EarlyWarningProcessingService


class EarlyWarningGraphTests(unittest.IsolatedAsyncioTestCase):
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
            source_kind=SourceKind.MAJOR_NEWS,
            trust_tier=TrustTier.HIGH,
        )

        assert incident is not None
        self.assertEqual(incident.incident_type, "company_withdrawal")
        self.assertEqual(incident.primary_source_url, record.payload["canonical_url"])
        self.assertEqual(incident.evidence[0].content_hash, "abc")

    async def test_irrelevant_page_is_not_converted(self) -> None:
        record = ScrapedRecallRecord(
            source_name="example",
            payload={"source_url": "https://example.test/advice", "visible_text": "Generic advice"},
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


if __name__ == "__main__":
    unittest.main()
