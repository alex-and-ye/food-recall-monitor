import json
import unittest
from datetime import date, datetime, timezone
from typing import Any, cast

from db.chroma_early_warning_client import (
    EarlyWarningIncidentsChromaClient,
    InMemoryEarlyWarningIncidentStore,
)
from models.early_warning_incident import (
    EarlyWarningIncidentCreate,
    IncidentEvidence,
    IncidentType,
    SourceKind,
    VerificationStatus,
    deserialize_evidence,
    serialize_evidence,
)
from services.early_warning.incidents import EarlyWarningIncidentService


class IncidentEvidenceSerializationTests(unittest.TestCase):
    def test_evidence_round_trips_as_chroma_safe_json(self) -> None:
        evidence = [
            IncidentEvidence(
                url="https://news.example.test/story",
                title="Product safety warning",
                publication_date=date(2026, 7, 20),
                source_kind=SourceKind.MAJOR_NEWS,
                content_hash="abc123",
            )
        ]

        encoded = serialize_evidence(evidence)
        decoded = deserialize_evidence(encoded)

        self.assertEqual(decoded, evidence)
        self.assertIsInstance(encoded, str)
        self.assertIsInstance(json.loads(encoded), list)


class InMemoryIncidentStoreTests(unittest.TestCase):
    def test_save_is_idempotent_and_updates_same_url(self) -> None:
        store = InMemoryEarlyWarningIncidentStore()
        service = EarlyWarningIncidentService(store)
        first_seen = datetime(2026, 7, 20, 12, tzinfo=timezone.utc)
        first = _incident(summary="Initial report", first_discovered_at=first_seen)

        created = service.save_incident(first)
        updated = service.save_incident(
            _incident(
                summary="Corrected report",
                hazard_type="Listeria monocytogenes",
                first_discovered_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
            )
        )

        self.assertEqual(updated.incident_id, created.incident_id)
        self.assertEqual(store.count_incidents(), 1)
        self.assertEqual(updated.summary, "Corrected report")
        self.assertEqual(updated.first_discovered_at, first_seen)
        self.assertEqual(len(updated.evidence), 1)

    def test_filters_and_returns_defensive_copies(self) -> None:
        store = InMemoryEarlyWarningIncidentStore()
        service = EarlyWarningIncidentService(store)
        created = service.save_incident(_incident())

        listed = store.list_incidents(
            verification_status=VerificationStatus.PENDING,
            incident_type=IncidentType.POTENTIAL_RECALL,
            minimum_confidence=70,
            country="canada",
            source_kind=SourceKind.MAJOR_NEWS,
        )
        listed[0].evidence.append(IncidentEvidence(url="https://mutated.example"))

        self.assertEqual([item.incident_id for item in listed], [created.incident_id])
        stored = store.get_incident(created.incident_id)
        assert stored is not None
        self.assertEqual(len(stored.evidence), 1)

    def test_incident_metadata_contains_only_chroma_scalar_values(self) -> None:
        incident = EarlyWarningIncidentService(
            InMemoryEarlyWarningIncidentStore()
        ).save_incident(_incident())

        metadata = incident.to_metadata()

        self.assertTrue(
            all(isinstance(value, str | int | float | bool) for value in metadata.values())
        )
        self.assertEqual(
            deserialize_evidence(metadata["evidence_json"]),
            incident.evidence,
        )
        restored = type(incident).from_metadata(metadata)
        self.assertEqual(restored, incident)

    def test_chroma_collection_is_separate_from_official_recalls(self) -> None:
        self.assertEqual(
            EarlyWarningIncidentsChromaClient.COLLECTION_NAME,
            "early_warning_incidents_collection",
        )


class ChromaIncidentRepositoryTests(unittest.TestCase):
    def test_upsert_and_read_round_trip_nested_evidence(self) -> None:
        client = cast(Any, object.__new__(EarlyWarningIncidentsChromaClient))
        client.collection = FakeIncidentCollection()
        incident = EarlyWarningIncidentService(
            InMemoryEarlyWarningIncidentStore()
        ).save_incident(_incident())

        client.upsert_incident(incident)
        restored = client.get_incident(incident.incident_id)

        self.assertEqual(restored, incident)
        self.assertEqual(len(client.collection.records), 1)
        stored_metadata = client.collection.records[incident.incident_id][1]
        self.assertIsInstance(stored_metadata["evidence_json"], str)

    def test_upsert_replaces_same_incident_id(self) -> None:
        client = cast(Any, object.__new__(EarlyWarningIncidentsChromaClient))
        client.collection = FakeIncidentCollection()
        incident = EarlyWarningIncidentService(
            InMemoryEarlyWarningIncidentStore()
        ).save_incident(_incident())

        client.upsert_incident(incident)
        client.upsert_incident(incident.model_copy(update={"summary": "Updated"}))

        self.assertEqual(client.count_incidents(), 1)
        restored = client.get_incident(incident.incident_id)
        assert restored is not None
        self.assertEqual(restored.summary, "Updated")


class FakeIncidentCollection:
    def __init__(self) -> None:
        self.records: dict[str, tuple[str, dict[str, object]]] = {}

    def upsert(self, *, ids, documents, metadatas) -> None:
        for incident_id, document, metadata in zip(
            ids,
            documents,
            metadatas,
            strict=True,
        ):
            self.records[incident_id] = (document, metadata)

    def get(self, *, ids=None, include=None):
        selected_ids = ids or sorted(self.records)
        found_ids = [incident_id for incident_id in selected_ids if incident_id in self.records]
        return {
            "ids": found_ids,
            "documents": [self.records[incident_id][0] for incident_id in found_ids],
            "metadatas": [self.records[incident_id][1] for incident_id in found_ids],
        }

    def delete(self, *, ids) -> None:
        for incident_id in ids:
            self.records.pop(incident_id, None)


def _incident(
    *,
    summary: str = "A publisher reports a possible safety issue.",
    hazard_type: str = "Listeria",
    first_discovered_at: datetime | None = None,
) -> EarlyWarningIncidentCreate:
    discovered_at = first_discovered_at or datetime(
        2026,
        7,
        20,
        12,
        tzinfo=timezone.utc,
    )
    return EarlyWarningIncidentCreate(
        incident_type=IncidentType.POTENTIAL_RECALL,
        product_name="Sample cheese",
        company_name="Sample Foods",
        hazard_type=hazard_type,
        summary=summary,
        country="Canada",
        publication_date=date(2026, 7, 20),
        first_discovered_at=discovered_at,
        last_discovered_at=discovered_at,
        primary_source_url="https://news.example.test/story?utm_source=test",
        primary_source_domain="news.example.test",
        primary_publisher="Example News",
        source_kind=SourceKind.MAJOR_NEWS,
        evidence=[
            IncidentEvidence(
                url="https://news.example.test/story",
                title="Sample cheese safety report",
                publication_date=date(2026, 7, 20),
                source_kind=SourceKind.MAJOR_NEWS,
                domain="news.example.test",
                content_hash="content-1",
            )
        ],
        extraction_completeness=0.9,
    )


if __name__ == "__main__":
    unittest.main()
