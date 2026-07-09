import unittest
from datetime import date
from typing import Any, cast
from unittest.mock import MagicMock

from db.chroma_client import FoodRecallAlertsChromaClient
from models.food_recall_alert import FoodRecallAlert, api_source_to_country_source

class AlertSearchModelTests(unittest.TestCase):
    def test_api_source_to_country_source_maps_known_sources(self) -> None:
        self.assertEqual(api_source_to_country_source("uk"), "UK")
        self.assertEqual(api_source_to_country_source("germany"), "Germany")
        self.assertEqual(api_source_to_country_source("france"), "France")

    def test_api_source_to_country_source_preserves_unknown_values(self) -> None:
        self.assertEqual(api_source_to_country_source("ca"), "ca")

    def test_from_metadata_derives_country_source_from_api_source(self) -> None:
        alert = FoodRecallAlert.from_metadata(
            {
                "alert_id": "alert-1",
                "api_source": "uk",
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

    def test_matches_search_checks_all_fields(self) -> None:
        alert = _alert(
            alert_id="batch-search-id",
            product_name="Chocolate Bar",
            source_url="https://example.com/recall/chocolate",
        )

        self.assertTrue(alert.matches_search("UK"))
        self.assertTrue(alert.matches_search("chocolate"))
        self.assertTrue(alert.matches_search("2026-06-09"))
        self.assertTrue(alert.matches_search("Ontario"))
        self.assertFalse(alert.matches_search("peanut butter"))

class ChromaClientSearchTests(unittest.TestCase):
    def test_search_alerts_filters_by_risk_level_country_source_and_search(self) -> None:
        client = cast(Any, object.__new__(FoodRecallAlertsChromaClient))
        client.collection = MagicMock()
        client.collection.get.return_value = {
            "metadatas": [
                _metadata(
                    alert_id="uk-high",
                    api_source="uk",
                    product_name="Cheese",
                    risk_level="High",
                ),
                _metadata(
                    alert_id="france-medium",
                    api_source="france",
                    product_name="Wine",
                    risk_level="Medium",
                ),
                _metadata(
                    alert_id="germany-low",
                    api_source="germany",
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
    api_source: str = "uk",
    product_name: str = "Sample Product",
    source_url: str = "https://example.com/recall",
) -> FoodRecallAlert:
    return FoodRecallAlert(
        alert_id=alert_id,
        api_source=api_source,
        country_source=api_source_to_country_source(api_source),
        product_name=product_name,
        product_category="Produce",
        recall_reason="Possible contamination",
        summary="This product was recalled.",
        recall_date=date(2026, 6, 9),
        risk_level="High",
        hazard_type="Listeria",
        consumer_action="Do not consume it.",
        source_url=source_url,
        affected_regions=["Ontario"],
    )

def _metadata(
    *,
    alert_id: str,
    api_source: str,
    product_name: str,
    risk_level: str,
) -> dict[str, str]:
    return {
        "alert_id": alert_id,
        "api_source": api_source,
        "country_source": api_source_to_country_source(api_source),
        "product_name": product_name,
        "product_category": "Produce",
        "recall_reason": "Reason",
        "summary": "Summary",
        "recall_date": "2026-01-01",
        "risk_level": risk_level,
        "hazard_type": "Unknown",
        "consumer_action": "Discard",
        "source_url": f"https://example.com/{alert_id}",
        "affected_regions": "[]",
    }

if __name__ == "__main__":
    unittest.main()