import unittest
from datetime import date
from unittest.mock import AsyncMock, patch

from models.food_recall_alert import FoodRecallAlertCreate
from services.geocoding import (
    Coordinates,
    apply_coordinate_jitter,
    average_coordinates,
    cleaned_affected_regions,
    fallback_coordinates,
    geocode_alert_location,
    region_geocode_query,
)

class GeocodingServiceTests(unittest.IsolatedAsyncioTestCase):
    def test_cleaned_affected_regions_skips_blank_values(self) -> None:
        alert = _alert(affected_regions=[" Bavaria ", "", "Berlin"])
        self.assertEqual(cleaned_affected_regions(alert), ["Bavaria", "Berlin"])

    def test_region_geocode_query_includes_country_source(self) -> None:
        self.assertEqual(
            region_geocode_query("Bavaria", "Germany"),
            "Bavaria, Germany",
        )

    def test_fallback_coordinates_uses_country_centers(self) -> None:
        alert = _alert(country_source="UK")
        self.assertEqual(fallback_coordinates(alert), Coordinates(55.3781, -3.4360))

    def test_average_coordinates_means_latitude_and_longitude(self) -> None:
        averaged = average_coordinates(
            [
                Coordinates(50.0, 10.0),
                Coordinates(52.0, 12.0),
            ]
        )
        self.assertEqual(averaged, Coordinates(51.0, 11.0))

    def test_apply_coordinate_jitter_stays_within_bounds(self) -> None:
        jittered = apply_coordinate_jitter(Coordinates(latitude=89.95, longitude=179.95))
        self.assertGreaterEqual(jittered.latitude, -90.0)
        self.assertLessEqual(jittered.latitude, 90.0)
        self.assertGreaterEqual(jittered.longitude, -180.0)
        self.assertLessEqual(jittered.longitude, 180.0)

    async def test_geocode_uses_country_when_no_affected_regions(self) -> None:
        alert = _alert(affected_regions=[], country_source="France")

        with (
            patch("services.geocoding.asyncio.sleep", new=AsyncMock()) as sleep_mock,
            patch(
                "services.geocoding._lookup_coordinates",
                return_value=Coordinates(46.2, 2.2),
            ) as lookup_mock,
            patch("services.geocoding.random.uniform", return_value=0.0),
        ):
            coordinates = await geocode_alert_location(alert)

        sleep_mock.assert_awaited_once_with(1.5)
        lookup_mock.assert_called_once_with("France")
        self.assertEqual(coordinates, Coordinates(46.2, 2.2))

    async def test_geocode_uses_region_and_country_for_single_region(self) -> None:
        alert = _alert(affected_regions=["Paris"], country_source="France")

        with (
            patch("services.geocoding.asyncio.sleep", new=AsyncMock()) as sleep_mock,
            patch(
                "services.geocoding._lookup_coordinates",
                return_value=Coordinates(48.8566, 2.3522),
            ) as lookup_mock,
            patch("services.geocoding.random.uniform", side_effect=[0.01, -0.02]),
        ):
            coordinates = await geocode_alert_location(alert)

        sleep_mock.assert_awaited_once_with(1.5)
        lookup_mock.assert_called_once_with("Paris, France")
        self.assertAlmostEqual(coordinates.latitude, 48.8666)
        self.assertAlmostEqual(coordinates.longitude, 2.3322)

    async def test_geocode_averages_multiple_regions(self) -> None:
        alert = _alert(
            affected_regions=["Bavaria", "Berlin"],
            country_source="Germany",
        )

        with (
            patch("services.geocoding.asyncio.sleep", new=AsyncMock()) as sleep_mock,
            patch(
                "services.geocoding._lookup_coordinates",
                side_effect=[
                    Coordinates(48.8, 11.5),
                    Coordinates(52.5, 13.4),
                ],
            ) as lookup_mock,
            patch("services.geocoding.random.uniform", return_value=0.0),
        ):
            coordinates = await geocode_alert_location(alert)

        self.assertEqual(sleep_mock.await_count, 2)
        self.assertEqual(
            [call.args[0] for call in lookup_mock.call_args_list],
            ["Bavaria, Germany", "Berlin, Germany"],
        )
        self.assertAlmostEqual(coordinates.latitude, 50.65)
        self.assertAlmostEqual(coordinates.longitude, 12.45)

    async def test_geocode_falls_back_to_country_center_when_lookups_fail(self) -> None:
        alert = _alert(affected_regions=["Unknown Place"], country_source="Germany")

        with (
            patch("services.geocoding.asyncio.sleep", new=AsyncMock()),
            patch("services.geocoding._lookup_coordinates", return_value=None),
            patch("services.geocoding.random.uniform", return_value=0.0),
        ):
            coordinates = await geocode_alert_location(alert)

        self.assertEqual(coordinates, Coordinates(51.1657, 10.4515))

def _alert(
    *,
    affected_regions: list[str] | None = None,
    country_source: str = "UK",
) -> FoodRecallAlertCreate:
    return FoodRecallAlertCreate(
        web_source="uk",
        country_source=country_source,
        product_name="Sample Product",
        product_category="Produce",
        recall_reason="Possible contamination",
        summary="This product was recalled.",
        recall_date=date(2026, 6, 9),
        risk_level="High",
        hazard_type="Listeria",
        consumer_action="Do not consume it.",
        source_url="https://example.com/recall",
        affected_regions=affected_regions if affected_regions is not None else [],
    )

if __name__ == "__main__":
    unittest.main()
