import unittest
from datetime import date
from typing import Any, cast
from unittest.mock import MagicMock, patch

from db.chroma_client import FoodRecallAlertsChromaClient
from models.food_recall_alert import FoodRecallAlertCreate, web_source_to_country_source

class ChromaClientDedupeTests(unittest.TestCase):
    def test_init_uses_server_based_http_client(self) -> None:
        fake_collection = object()
        fake_http_client = MagicMock()
        fake_http_client.get_or_create_collection.return_value = fake_collection

        with patch("db.chroma_client.chromadb.HttpClient", return_value=fake_http_client) as http_client:
            client = FoodRecallAlertsChromaClient(host="chroma", port=9000)

        http_client.assert_called_once_with(host="chroma", port=9000)
        fake_http_client.get_or_create_collection.assert_called_once_with(
            name=FoodRecallAlertsChromaClient.COLLECTION_NAME
        )
        self.assertIs(client.collection, fake_collection)

    def test_save_alerts_assigns_uuid_and_skips_duplicate_dedupe_keys(self) -> None:
        client = cast(Any, object.__new__(FoodRecallAlertsChromaClient))
        client.collection = FakeCollection()
        alert = _alert()

        inserted = client.save_alerts([alert, alert])

        self.assertEqual(len(inserted), 1)
        self.assertEqual(len(client.collection.added["ids"]), 1)
        self.assertTrue(client.collection.added["ids"][0])
        self.assertEqual(client.collection.added["metadatas"][0]["web_source"], "test-source")
        self.assertEqual(client.collection.added["metadatas"][0]["product_name"], "Sample Product")
        self.assertEqual(client.collection.added["metadatas"][0]["latitude"], 0.0)
        self.assertEqual(client.collection.added["metadatas"][0]["longitude"], 0.0)
        self.assertIn("dedupe_key", client.collection.added["metadatas"][0])

        second_insert = client.save_alerts([alert])

        self.assertEqual(len(second_insert), 0)
        self.assertEqual(len(client.collection.added["ids"]), 1)

    def test_dedupe_key_uses_product_name_recall_date_and_source_url(self) -> None:
        first = _alert()
        same = _alert()
        changed_url = _alert(source_url="https://example.com/changed")

        self.assertEqual(
            FoodRecallAlertsChromaClient._build_dedupe_key(first),
            FoodRecallAlertsChromaClient._build_dedupe_key(same),
        )
        self.assertNotEqual(
            FoodRecallAlertsChromaClient._build_dedupe_key(first),
            FoodRecallAlertsChromaClient._build_dedupe_key(changed_url),
        )

    def test_save_alerts_returns_zero_for_empty_input(self) -> None:
        client = cast(Any, object.__new__(FoodRecallAlertsChromaClient))
        client.collection = MagicMock()

        inserted = client.save_alerts([])

        self.assertEqual(inserted, [])
        client.collection.add.assert_not_called()

    def test_save_alerts_updates_corrected_alert_with_same_source_url(self) -> None:
        client = cast(Any, object.__new__(FoodRecallAlertsChromaClient))
        client.collection = FakeCollection()
        original = _alert(recall_date=date(2026, 7, 11))
        corrected = _alert(recall_date=date(2026, 7, 10))

        self.assertEqual(len(client.save_alerts([original])), 1)
        original_id = client.collection.added["ids"][0]
        self.assertEqual(len(client.save_alerts([corrected])), 0)

        self.assertEqual(client.collection.updated["ids"], [original_id])
        self.assertEqual(
            client.collection.updated["metadatas"][0]["recall_date"],
            "2026-07-10",
        )

    def test_get_alerts_returns_empty_when_collection_has_no_metadata(self) -> None:
        client = cast(Any, object.__new__(FoodRecallAlertsChromaClient))
        client.collection = MagicMock()
        client.collection.get.return_value = {"metadatas": []}

        alerts = client.get_alerts()

        self.assertEqual(alerts, [])

    def test_get_alerts_skips_none_metadata_and_sorts_by_recall_date_desc(self) -> None:
        client = cast(Any, object.__new__(FoodRecallAlertsChromaClient))
        client.collection = MagicMock()
        client.collection.get.return_value = {
            "metadatas": [
                {
                    "alert_id": "older",
                    "web_source": "test-source",
                    "product_name": "Old Product",
                    "product_category": "Produce",
                    "recall_reason": "Reason",
                    "summary": "Old summary",
                    "recall_date": "2025-01-01",
                    "risk_level": "Low",
                    "hazard_type": "Unknown",
                    "consumer_action": "Discard",
                    "source_url": "https://example.com/old",
                    "affected_regions": "[]",
                },
                None,
                {
                    "alert_id": "newer",
                    "web_source": "test-source",
                    "product_name": "New Product",
                    "product_category": "Produce",
                    "recall_reason": "Reason",
                    "summary": "New summary",
                    "recall_date": "2026-01-01",
                    "risk_level": "High",
                    "hazard_type": "Listeria",
                    "consumer_action": "Discard",
                    "source_url": "https://example.com/new",
                    "affected_regions": "[]",
                },
            ]
        }

        alerts = client.get_alerts()

        self.assertEqual([alert.alert_id for alert in alerts], ["newer", "older"])

    def test_get_alert_by_id_returns_alert_when_found(self) -> None:
        client = cast(Any, object.__new__(FoodRecallAlertsChromaClient))
        client.collection = MagicMock()
        client.collection.get.return_value = {
            "metadatas": [
                {
                    "alert_id": "alert-123",
                    "web_source": "test-source",
                    "product_name": "Sample Product",
                    "product_category": "Produce",
                    "recall_reason": "Reason",
                    "summary": "Summary",
                    "recall_date": "2026-06-09",
                    "risk_level": "High",
                    "hazard_type": "Listeria",
                    "consumer_action": "Discard",
                    "source_url": "https://example.com/recall",
                    "affected_regions": "[]",
                }
            ]
        }

        alert = client.get_alert_by_id("alert-123")

        self.assertIsNotNone(alert)
        assert alert is not None
        self.assertEqual(alert.alert_id, "alert-123")
        self.assertEqual(alert.product_name, "Sample Product")
        client.collection.get.assert_called_once_with(ids=["alert-123"], include=["metadatas"])

    def test_get_alert_by_id_returns_none_when_not_found(self) -> None:
        client = cast(Any, object.__new__(FoodRecallAlertsChromaClient))
        client.collection = MagicMock()
        client.collection.get.return_value = {"metadatas": []}

        alert = client.get_alert_by_id("missing-id")

        self.assertIsNone(alert)

    def test_get_alert_by_id_returns_none_when_metadata_is_none(self) -> None:
        client = cast(Any, object.__new__(FoodRecallAlertsChromaClient))
        client.collection = MagicMock()
        client.collection.get.return_value = {"metadatas": [None]}

        alert = client.get_alert_by_id("alert-123")

        self.assertIsNone(alert)

    def test_get_existing_dedupe_keys_ignores_missing_values(self) -> None:
        client = cast(Any, object.__new__(FoodRecallAlertsChromaClient))
        client.collection = MagicMock()
        client.collection.get.return_value = {
            "metadatas": [
                {"dedupe_key": "abc"},
                {"dedupe_key": ""},
                {},
                None,
            ]
        }

        keys = client._get_existing_dedupe_keys(["abc", "def"])

        self.assertEqual(keys, {"abc"})

class FakeCollection:
    def __init__(self) -> None:
        self.existing_dedupe_keys: set[str] = set()
        self.added = {
            "ids": [],
            "documents": [],
            "metadatas": [],
        }
        self.updated = {
            "ids": [],
            "documents": [],
            "metadatas": [],
        }

    def get(self, *, where=None, include=None):
        source_urls = set((where or {}).get("source_url", {}).get("$in", []))
        if source_urls:
            matches = [
                (record_id, metadata)
                for record_id, metadata in zip(
                    self.added["ids"],
                    self.added["metadatas"],
                    strict=True,
                )
                if metadata["source_url"] in source_urls
            ]
            return {
                "ids": [record_id for record_id, _metadata in matches],
                "metadatas": [metadata for _record_id, metadata in matches],
            }
        requested_keys = set((where or {}).get("dedupe_key", {}).get("$in", []))
        return {
            "ids": [],
            "metadatas": [
                {"dedupe_key": key}
                for key in self.existing_dedupe_keys.intersection(requested_keys)
            ]
        }

    def add(self, *, ids, documents, metadatas) -> None:
        self.added["ids"].extend(ids)
        self.added["documents"].extend(documents)
        self.added["metadatas"].extend(metadatas)
        self.existing_dedupe_keys.update(metadata["dedupe_key"] for metadata in metadatas)

    def update(self, *, ids, documents, metadatas) -> None:
        self.updated["ids"].extend(ids)
        self.updated["documents"].extend(documents)
        self.updated["metadatas"].extend(metadatas)
        for record_id, metadata in zip(ids, metadatas, strict=True):
            index = self.added["ids"].index(record_id)
            old_key = self.added["metadatas"][index]["dedupe_key"]
            self.existing_dedupe_keys.discard(old_key)
            self.added["documents"][index] = documents[ids.index(record_id)]
            self.added["metadatas"][index] = metadata
            self.existing_dedupe_keys.add(metadata["dedupe_key"])


def _alert(
    source_url: str = "https://example.com/recall",
    recall_date: date = date(2026, 6, 9),
) -> FoodRecallAlertCreate:
    return FoodRecallAlertCreate(
        web_source="test-source",
        country_source=web_source_to_country_source("test-source"),
        product_name="Sample Product",
        product_category="Produce",
        recall_reason="Possible contamination",
        summary="This product was recalled. It may be unsafe. Consumers should not eat it.",
        recall_date=recall_date,
        risk_level="High",
        hazard_type="Listeria",
        consumer_action="Do not consume it.",
        source_url=source_url,
        affected_regions=["Ontario"],
    )

if __name__ == "__main__":
    unittest.main()
