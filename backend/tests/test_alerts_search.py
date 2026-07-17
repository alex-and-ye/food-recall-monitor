import unittest
from datetime import date
from typing import Any, cast
from unittest.mock import MagicMock

from db.chroma_client import FoodRecallAlertsChromaClient
from models.food_recall_alert import FoodRecallAlert, web_source_to_country_source

class AlertSearchModelTests(unittest.TestCase):
    def test_web_source_to_country_source_maps_known_sources(self) -> None:
        self.assertEqual(web_source_to_country_source("uk"), "UK")
        self.assertEqual(web_source_to_country_source("germany"), "Germany")
        self.assertEqual(web_source_to_country_source("france"), "France")

    def test_web_source_to_country_source_preserves_unknown_values(self) -> None:
        self.assertEqual(web_source_to_country_source("ca"), "ca")

    def test_from_metadata_derives_country_source_from_web_source(self) -> None:
        alert = FoodRecallAlert.from_metadata(
            {
                "alert_id": "alert-1",
                "web_source": "uk",
                "product_name": "Milk",
                "product_category": "Dairy",
                "recall_reason": "Contamination",
                "summary": "Summary",
                "recall_date": "2026-01-01",
                "risk_level": "High",
                "hazard_type": "Bacteria",
                "consumer_action": "Return",
                "source_url": "https://example.com",
                "affected_regions": "[]",
            }
        )

        self.assertEqual(alert.country_source, "UK")
        self.assertEqual(alert.web_source, "uk")
        self.assertEqual(alert.batch_id, "")

    def test_from_metadata_accepts_legacy_api_source_key(self) -> None:
        alert = FoodRecallAlert.from_metadata(
            {
                "alert_id": "alert-legacy",
                "api_source": "france",
                "product_name": "Cheese",
                "product_category": "Dairy",
                "recall_reason": "Contamination",
                "summary": "Summary",
                "recall_date": "2026-01-01",
                "risk_level": "High",
                "hazard_type": "Bacteria",
                "consumer_action": "Return",
                "source_url": "https://example.com",
                "affected_regions": "[]",
            }
        )

        self.assertEqual(alert.web_source, "france")
        self.assertEqual(alert.country_source, "France")

    def test_to_metadata_omits_empty_batch_id_and_round_trips(self) -> None:
        with_batch = _alert(batch_id="LOT-42")
        without_batch = _alert(batch_id="")

        with_meta = with_batch.to_metadata()
        without_meta = without_batch.to_metadata()

        self.assertEqual(with_meta["batch_id"], "LOT-42")
        self.assertNotIn("batch_id", without_meta)
        self.assertEqual(FoodRecallAlert.from_metadata(with_meta).batch_id, "LOT-42")
        self.assertEqual(FoodRecallAlert.from_metadata(without_meta).batch_id, "")

    def test_matches_search_checks_all_fields(self) -> None:
        alert = _alert(
            alert_id="batch-search-id",
            product_name="Chocolate Bar",
            source_url="https://example.com/recall/chocolate",
            batch_id="LOT-CHOC-99",
        )

        self.assertTrue(alert.matches_search("UK"))
        self.assertTrue(alert.matches_search("chocolate"))
        self.assertTrue(alert.matches_search("2026-06-09"))
        self.assertTrue(alert.matches_search("Ontario"))
        self.assertTrue(alert.matches_search("LOT-CHOC-99"))
        self.assertFalse(alert.matches_search("peanut butter"))

class ChromaClientSearchTests(unittest.TestCase):
    def test_search_alerts_filters_by_risk_level_country_source_and_search(self) -> None:
        client = cast(Any, object.__new__(FoodRecallAlertsChromaClient))
        client.collection = MagicMock()
        client.collection.get.return_value = {
            "metadatas": [
                _metadata(
                    alert_id="uk-high",
                    web_source="uk",
                    product_name="Cheese",
                    risk_level="High",
                ),
                _metadata(
                    alert_id="france-medium",
                    web_source="france",
                    product_name="Wine",
                    risk_level="Medium",
                ),
                _metadata(
                    alert_id="germany-low",
                    web_source="germany",
                    product_name="Bread",
                    risk_level="Low",
                ),
            ]
        }

        risk_filtered = client.search_alerts(risk_level="High")
        self.assertEqual([alert.alert_id for alert in risk_filtered], ["uk-high"])

        country_filtered = client.search_alerts(country_source="France")
        self.assertEqual(
            [alert.alert_id for alert in country_filtered],
            ["france-medium"],
        )

        search_filtered = client.search_alerts(search="bread")
        self.assertEqual(
            [alert.alert_id for alert in search_filtered],
            ["germany-low"],
        )

        combined_filtered = client.search_alerts(
            search="cheese",
            risk_level="High",
            country_source="UK",
        )
        self.assertEqual(
            [alert.alert_id for alert in combined_filtered],
            ["uk-high"],
        )

    def test_search_alerts_filters_by_recall_date(self) -> None:
        client = cast(Any, object.__new__(FoodRecallAlertsChromaClient))
        client.collection = MagicMock()
        client.collection.get.return_value = {
            "metadatas": [
                _metadata(
                    alert_id="alert-june-22",
                    web_source="uk",
                    product_name="Cheese",
                    risk_level="High",
                    recall_date="2026-06-22",
                ),
                _metadata(
                    alert_id="alert-june-21",
                    web_source="uk",
                    product_name="Milk",
                    risk_level="Medium",
                    recall_date="2026-06-21",
                ),
            ]
        }

        date_filtered = client.search_alerts(recall_date=date(2026, 6, 22))
        self.assertEqual(
            [alert.alert_id for alert in date_filtered],
            ["alert-june-22"],
        )

    def test_search_alerts_sorts_by_recall_date(self) -> None:
        client = cast(Any, object.__new__(FoodRecallAlertsChromaClient))
        client.collection = MagicMock()
        client.collection.get.return_value = {
            "metadatas": [
                _metadata(
                    alert_id="alert-newest",
                    web_source="uk",
                    product_name="Cheese",
                    risk_level="High",
                    recall_date="2026-06-22",
                ),
                _metadata(
                    alert_id="alert-middle",
                    web_source="uk",
                    product_name="Milk",
                    risk_level="Medium",
                    recall_date="2026-06-21",
                ),
                _metadata(
                    alert_id="alert-oldest",
                    web_source="uk",
                    product_name="Bread",
                    risk_level="Low",
                    recall_date="2026-06-20",
                ),
            ]
        }

        latest_sorted = client.search_alerts(sort_by="latest")
        self.assertEqual(
            [alert.alert_id for alert in latest_sorted],
            ["alert-newest", "alert-middle", "alert-oldest"],
        )

        oldest_sorted = client.search_alerts(sort_by="oldest")
        self.assertEqual(
            [alert.alert_id for alert in oldest_sorted],
            ["alert-oldest", "alert-middle", "alert-newest"],
        )

    def test_get_alerts_version_returns_count_and_fingerprint(self) -> None:
        client = cast(Any, object.__new__(FoodRecallAlertsChromaClient))
        client.collection = MagicMock()
        client.collection.get.return_value = {
            "ids": ["alert-b", "alert-a", "alert-c"],
        }

        version = client.get_alerts_version()

        self.assertEqual(version.count, 3)
        self.assertEqual(len(version.fingerprint), 64)

def _alert(
    *,
    alert_id: str = "alert-1",
    web_source: str = "uk",
    product_name: str = "Sample Product",
    source_url: str = "https://example.com/recall",
    batch_id: str = "",
) -> FoodRecallAlert:
    return FoodRecallAlert(
        alert_id=alert_id,
        web_source=web_source,
        country_source=web_source_to_country_source(web_source),
        product_name=product_name,
        product_category="Produce",
        recall_reason="Possible contamination",
        summary="This product was recalled.",
        recall_date=date(2026, 6, 9),
        risk_level="High",
        hazard_type="Listeria",
        consumer_action="Do not consume it.",
        source_url=source_url,
        batch_id=batch_id,
        affected_regions=["Ontario"],
    )

def _metadata(
    *,
    alert_id: str,
    web_source: str,
    product_name: str,
    risk_level: str,
    recall_date: str = "2026-01-01",
) -> dict[str, str]:
    return {
        "alert_id": alert_id,
        "web_source": web_source,
        "country_source": web_source_to_country_source(web_source),
        "product_name": product_name,
        "product_category": "Produce",
        "recall_reason": "Reason",
        "summary": "Summary",
        "recall_date": recall_date,
        "risk_level": risk_level,
        "hazard_type": "Unknown",
        "consumer_action": "Discard",
        "source_url": f"https://example.com/{alert_id}",
        "affected_regions": "[]",
    }

if __name__ == "__main__":
    unittest.main()