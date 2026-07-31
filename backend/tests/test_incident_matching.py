import unittest
from datetime import date, datetime, timezone
from types import SimpleNamespace

from db.chroma_early_warning_client import InMemoryEarlyWarningIncidentStore
from models.early_warning_incident import (
    EarlyWarningIncident,
    IncidentEvidence,
    IncidentType,
    SourceKind,
    VerificationStatus,
)
from models.food_recall_alert import FoodRecallAlert
from services.early_warning.matching import (
    IncidentMatcher,
    MatchKind,
    canonicalize_url,
)
from services.early_warning.incidents import EarlyWarningIncidentService
from services.early_warning.verification import IncidentVerificationService

class IncidentMatcherTests(unittest.TestCase):
    def test_canonical_url_match_is_checked_first(self) -> None:
        incoming = _incident(
            "incoming",
            url="https://Example.test/report/?utm_source=news#details",
            content_hash="incoming-hash",
            title="Different title",
        )
        existing = _incident(
            "existing",
            url="https://example.test/report",
            content_hash="existing-hash",
            title="Original title",
        )

        result = IncidentMatcher().find_match(incoming, [existing])

        assert result is not None
        self.assertEqual(result.kind, MatchKind.EXACT_URL)
        self.assertEqual(
            canonicalize_url(incoming.primary_source_url),
            "https://example.test/report",
        )

    def test_content_hash_precedes_title_and_entity_matching(self) -> None:
        incoming = _incident(
            "incoming",
            url="https://one.example/story",
            content_hash="same-content",
            title="Incoming title",
        )
        existing = _incident(
            "existing",
            url="https://two.example/story",
            content_hash="same-content",
            title="Existing title",
        )

        result = IncidentMatcher().find_match(incoming, [existing])

        assert result is not None
        self.assertEqual(result.kind, MatchKind.CONTENT_HASH)

    def test_entity_match_respects_date_window(self) -> None:
        incoming = _incident("incoming", publication_date=date(2026, 7, 20))
        nearby = _incident("nearby", publication_date=date(2026, 7, 25))
        far = _incident("far", publication_date=date(2026, 8, 20))

        result = IncidentMatcher(date_window_days=7).find_match(incoming, [far, nearby])

        assert result is not None
        self.assertEqual(result.matched_id, "nearby")
        self.assertEqual(result.kind, MatchKind.ENTITY_DATE)

    def test_entity_match_ignores_country_label_aliases(self) -> None:
        incoming = _incident(
            "incoming",
            product_name="Chocolate Chip Brioche Rolls",
            company_name="Waitrose & Partners",
            country="UK",
            publication_date=date(2026, 7, 22),
            url="https://one.example/brioche",
        )
        existing = _incident(
            "existing",
            product_name="Chocolate Chip Brioche Rolls",
            company_name="Waitrose and Partners",
            country="United Kingdom",
            publication_date=date(2026, 7, 22),
            url="https://two.example/brioche",
        )

        result = IncidentMatcher().find_match(incoming, [existing])

        assert result is not None
        self.assertEqual(result.matched_id, "existing")
        self.assertEqual(result.kind, MatchKind.ENTITY_DATE)
        self.assertIn("product_name", result.entity_overlap)
        self.assertIn("company_name", result.entity_overlap)

    def test_save_merges_when_country_labels_differ(self) -> None:
        store = InMemoryEarlyWarningIncidentStore()
        service = EarlyWarningIncidentService(store)
        first = service.save_incident(
            _incident(
                "ignored-1",
                product_name="Chocolate Chip Brioche Rolls",
                company_name="Waitrose & Partners",
                country="United Kingdom",
                publication_date=date(2026, 7, 22),
                url="https://one.example/brioche",
            )
        )
        second = service.save_incident(
            _incident(
                "ignored-2",
                product_name="Chocolate Chip Brioche Rolls",
                company_name="Waitrose and Partners",
                country="UK",
                publication_date=date(2026, 7, 22),
                url="https://two.example/brioche",
            )
        )

        self.assertEqual(first.incident_id, second.incident_id)
        self.assertEqual(store.count_incidents(), 1)
        stored = store.get_incident(first.incident_id)
        assert stored is not None
        self.assertEqual(stored.country, "United Kingdom")
        self.assertEqual(len(stored.evidence), 2)

    def test_entity_match_allows_missing_dates_when_product_and_company_align(self) -> None:
        incoming = _incident(
            "incoming",
            product_name="Chocolate Chip Brioche Rolls",
            company_name="Waitrose & Partners",
            publication_date=None,
            url="https://one.example/brioche",
        )
        existing = _incident(
            "existing",
            product_name="8 Chocolate Chip Brioche Rolls",
            company_name="Waitrose and Partners",
            publication_date=None,
            url="https://two.example/brioche",
        )

        result = IncidentMatcher().find_match(incoming, [existing])

        assert result is not None
        self.assertEqual(result.kind, MatchKind.ENTITY_DATE)

    def test_semantic_matching_never_merges_without_entity_overlap(self) -> None:
        calls = 0

        def score(_left: EarlyWarningIncident, _right: EarlyWarningIncident) -> float:
            nonlocal calls
            calls += 1
            return 0.99

        incoming = _incident("incoming", product_name="Product A", hazard_type="Listeria")
        unrelated = _incident(
            "unrelated",
            product_name="Product B",
            company_name="Other Co",
            hazard_type="Salmonella",
            country="France",
        )

        result = IncidentMatcher(semantic_scorer=score).find_match(incoming, [unrelated])

        self.assertIsNone(result)
        self.assertEqual(calls, 0)

    def test_semantic_score_is_pluggable_and_borderline_requires_review(self) -> None:
        incoming = _incident("incoming", publication_date=date(2026, 7, 1))
        existing = _incident("existing", publication_date=date(2026, 8, 1))
        matcher = IncidentMatcher(semantic_scorer=lambda _left, _right: 0.87)

        result = matcher.find_match(incoming, [existing])

        assert result is not None
        self.assertEqual(result.kind, MatchKind.SEMANTIC)
        self.assertTrue(result.requires_review)
        self.assertIn("product_name", result.entity_overlap)

class VerificationTests(unittest.TestCase):
    def test_official_link_updates_only_incident(self) -> None:
        store = InMemoryEarlyWarningIncidentStore()
        incident = _incident("incident")
        store.upsert_incident(incident)
        official = _official_alert()
        original_official = official.model_copy(deep=True)

        result = IncidentVerificationService(store).verify_incident(
            incident.incident_id,
            [official],
        )

        assert result is not None
        self.assertTrue(result.confirmed)
        self.assertEqual(
            result.incident.verification_status,
            VerificationStatus.OFFICIALLY_CONFIRMED,
        )
        self.assertEqual(result.incident.confidence_score, 100)
        self.assertEqual(result.incident.linked_official_alert_ids, ["official-1"])
        self.assertEqual(official, original_official)
        self.assertEqual(result.incident.first_discovered_at, incident.first_discovered_at)

class SemanticIndexGuardTests(unittest.TestCase):
    def test_high_similarity_merges_only_with_primary_entity_overlap(self) -> None:
        store = InMemoryEarlyWarningIncidentStore()
        existing = _incident("existing", publication_date=date(2026, 6, 1))
        store.upsert_incident(existing)
        semantic_index = _FakeSemanticIndex("existing", 0.95)
        service = EarlyWarningIncidentService(store, semantic_index=semantic_index)

        saved = service.save_incident(
            _incident("incoming", publication_date=date(2026, 7, 20))
        )

        self.assertEqual(saved.incident_id, "existing")
        self.assertEqual(store.count_incidents(), 1)
        self.assertTrue(semantic_index.upserted)

    def test_borderline_similarity_is_flagged_without_auto_merge(self) -> None:
        store = InMemoryEarlyWarningIncidentStore()
        store.upsert_incident(_incident("existing", publication_date=date(2026, 6, 1)))
        service = EarlyWarningIncidentService(
            store,
            semantic_index=_FakeSemanticIndex("existing", 0.86),
        )

        saved = service.save_incident(
            _incident("incoming", publication_date=date(2026, 7, 20))
        )

        self.assertEqual(store.count_incidents(), 2)
        self.assertTrue(
            any(reason.startswith("possible_duplicate:existing:") for reason in saved.processing_errors)
        )

class _FakeSemanticIndex:
    def __init__(self, record_id: str, score: float) -> None:
        self.record_id = record_id
        self.score = score
        self.upserted: list[str] = []

    def query_incidents(self, _incident, *, limit: int = 10):
        return [SimpleNamespace(record_id=self.record_id, score=self.score)][:limit]

    def upsert_incident(self, incident: EarlyWarningIncident) -> None:
        self.upserted.append(incident.incident_id)

def _incident(
    incident_id: str,
    *,
    url: str | None = None,
    content_hash: str = "",
    title: str = "",
    product_name: str = "Sample cheese",
    company_name: str = "Sample Foods",
    hazard_type: str = "Listeria",
    country: str = "Canada",
    publication_date: date = date(2026, 7, 20),
) -> EarlyWarningIncident:
    source_url = url or f"https://{incident_id}.example.test/story"
    discovered_at = datetime(2026, 7, 20, 12, tzinfo=timezone.utc)
    return EarlyWarningIncident(
        incident_id=incident_id,
        incident_type=IncidentType.POTENTIAL_RECALL,
        confidence_score=75,
        confidence_reasons=["fixture"],
        product_name=product_name,
        company_name=company_name,
        hazard_type=hazard_type,
        summary="A cautious incident summary.",
        country=country,
        publication_date=publication_date,
        first_discovered_at=discovered_at,
        last_discovered_at=discovered_at,
        primary_source_url=source_url,
        primary_source_domain=f"{incident_id}.example.test",
        source_kind=SourceKind.MAJOR_NEWS,
        evidence=[
            IncidentEvidence(
                url=source_url,
                title=title,
                publication_date=publication_date,
                source_kind=SourceKind.MAJOR_NEWS,
                content_hash=content_hash,
            )
        ],
    )

def _official_alert() -> FoodRecallAlert:
    return FoodRecallAlert(
        alert_id="official-1",
        web_source="canada",
        country_source="Canada",
        product_name="Sample cheese",
        product_category="Dairy",
        recall_reason="Possible contamination",
        summary="Official recall summary.",
        recall_date=date(2026, 7, 22),
        risk_level="High",
        hazard_type="Listeria",
        consumer_action="Do not consume.",
        source_url="https://inspection.example.test/recall",
        affected_regions=["Canada"],
    )

if __name__ == "__main__":
    unittest.main()
