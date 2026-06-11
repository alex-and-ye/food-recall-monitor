import unittest
from datetime import date

from db.chroma_client import FoodRecallAlertsChromaClient
from models.food_recall_alert import FoodRecallAlertCreate

class ChromaClientDedupeTests(unittest.TestCase):
    def test_save_alerts_assigns_uuid_and_skips_duplicate_dedupe_keys(self) -> None:
        client = object.__new__(FoodRecallAlertsChromaClient)
        client.collection = FakeCollection()
        alert = _alert()

        inserted_count = client.save_alerts([alert, alert])

        self.assertEqual(inserted_count, 1)
        self.assertEqual(len(client.collection.added["ids"]), 1)
        self.assertTrue(client.collection.added["ids"][0])
        self.assertEqual(client.collection.added["metadatas"][0]["api_source"], "test-source")
        self.assertEqual(client.collection.added["metadatas"][0]["product_name"], "Sample Product")
        self.assertIn("dedupe_key", client.collection.added["metadatas"][0])

        second_insert_count = client.save_alerts([alert])

        self.assertEqual(second_insert_count, 0)
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

class FakeCollection:
    def __init__(self) -> None:
        self.existing_dedupe_keys: set[str] = set()
        self.added = {
            "ids": [],
            "documents": [],
            "metadatas": [],
        }

    def get(self, *, where=None, include=None):
        requested_keys = set((where or {}).get("dedupe_key", {}).get("$in", []))
        return {
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

def _alert(source_url: str = "https://example.com/recall") -> FoodRecallAlertCreate:
    return FoodRecallAlertCreate(
        api_source="test-source",
        product_name="Sample Product",
        product_category="Produce",
        recall_reason="Possible contamination",
        summary="This product was recalled. It may be unsafe. Consumers should not eat it.",
        recall_date=date(2026, 6, 9),
        risk_level="High",
        hazard_type="Listeria",
        consumer_action="Do not consume it.",
        source_url=source_url,
        affected_regions=["Ontario"],
    )

if __name__ == "__main__":
    unittest.main()
