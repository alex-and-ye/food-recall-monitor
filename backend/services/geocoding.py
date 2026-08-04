"""Geocode food-recall alert locations for map display.

Resolves representative latitude/longitude via Nominatim, with country-center
fallbacks and light jitter so overlapping pins remain distinguishable.
"""

import asyncio
import logging
import random
from typing import NamedTuple

from geopy.exc import GeocoderServiceError, GeocoderTimedOut
from geopy.geocoders import Nominatim
from geopy.location import Location

from models.food_recall_alert import CountrySource, FoodRecallAlertCreate

LOGGER: logging.Logger = logging.getLogger(__name__)  # Module logger for geocode failures.

NOMINATIM_REQUEST_DELAY_SECONDS: float = 1.5  # Courtesy delay between Nominatim requests.
COORDINATE_JITTER_DEGREES: float = 0.1  # Random offset so stacked pins separate slightly.

# Approximate country centroids used when live geocoding fails.
COUNTRY_CENTER_COORDINATES: dict[str, tuple[float, float]] = {
    CountrySource.FRANCE: (46.2276, 2.2137),
    CountrySource.GERMANY: (51.1657, 10.4515),
    CountrySource.UK: (55.3781, -3.4360),
    "United Kingdom": (55.3781, -3.4360),
}


class Coordinates(NamedTuple):
    """Latitude/longitude pair for a map pin.

    Attributes:
        latitude: Degrees north/south.
        longitude: Degrees east/west.
    """

    latitude: float
    longitude: float


_geolocator: Nominatim | None = None  # Lazily created Nominatim client singleton.


def _get_geolocator() -> Nominatim:
    """Return the shared Nominatim client, creating it on first use.

    Returns:
        Configured Nominatim geolocator instance.
    """
    global _geolocator
    if _geolocator is None:
        _geolocator = Nominatim(user_agent="food-recall-monitor")
    return _geolocator


def cleaned_affected_regions(alert: FoodRecallAlertCreate) -> list[str]:
    """Return non-empty, stripped affected-region labels from an alert.

    Args:
        alert: Alert create payload containing affected regions.

    Returns:
        Cleaned list of region strings.
    """
    regions: list[str] = []
    for region in alert.affected_regions:
        cleaned = region.strip()
        if cleaned:
            regions.append(cleaned)
    return regions


def country_geocode_query(alert: FoodRecallAlertCreate) -> str:
    """Build a country-level geocode query string.

    Args:
        alert: Alert whose country_source is used as the query.

    Returns:
        Stripped country name suitable for Nominatim.
    """
    return alert.country_source.strip()


def region_geocode_query(region: str, country_source: str) -> str:
    """Build a region-plus-country geocode query.

    Args:
        region: Affected region label.
        country_source: Country name to disambiguate the region.

    Returns:
        Query string of the form ``region, country`` when country is present.
    """
    country = country_source.strip()
    if country:
        return f"{region}, {country}"
    return region


def fallback_coordinates(alert: FoodRecallAlertCreate) -> Coordinates:
    """Return country-center coordinates, or (0, 0) when unknown.

    Args:
        alert: Alert whose country_source selects the fallback centroid.

    Returns:
        Fallback Coordinates for the alert's country.
    """
    country_key = alert.country_source.strip()
    if country_key in COUNTRY_CENTER_COORDINATES:
        latitude, longitude = COUNTRY_CENTER_COORDINATES[country_key]
        return Coordinates(latitude=latitude, longitude=longitude)

    mapped_key = country_key.title()
    if mapped_key in COUNTRY_CENTER_COORDINATES:
        latitude, longitude = COUNTRY_CENTER_COORDINATES[mapped_key]
        return Coordinates(latitude=latitude, longitude=longitude)

    return Coordinates(latitude=0.0, longitude=0.0)


def average_coordinates(coordinates_list: list[Coordinates]) -> Coordinates:
    """Average a non-empty list of coordinates into a single point.

    Args:
        coordinates_list: Coordinates to average.

    Returns:
        Mean latitude and longitude.

    Raises:
        ValueError: If ``coordinates_list`` is empty.
    """
    count = len(coordinates_list)
    if count == 0:
        raise ValueError("Cannot average an empty coordinates list")

    latitude_sum = sum(item.latitude for item in coordinates_list)
    longitude_sum = sum(item.longitude for item in coordinates_list)
    return Coordinates(
        latitude=latitude_sum / count,
        longitude=longitude_sum / count,
    )


def apply_coordinate_jitter(coordinates: Coordinates) -> Coordinates:
    """Apply a small random offset clamped to valid lat/lon ranges.

    Args:
        coordinates: Base coordinates before jitter.

    Returns:
        Jittered Coordinates within world bounds.
    """
    latitude = coordinates.latitude + random.uniform(
        -COORDINATE_JITTER_DEGREES,
        COORDINATE_JITTER_DEGREES,
    )
    longitude = coordinates.longitude + random.uniform(
        -COORDINATE_JITTER_DEGREES,
        COORDINATE_JITTER_DEGREES,
    )
    return Coordinates(
        latitude=max(-90.0, min(90.0, latitude)),
        longitude=max(-180.0, min(180.0, longitude)),
    )


def _lookup_coordinates(query: str) -> Coordinates | None:
    """Synchronously geocode a query via Nominatim.

    Args:
        query: Free-text place query.

    Returns:
        Coordinates on success, or None when lookup fails or query is empty.
    """
    if not query:
        return None

    try:
        location = _get_geolocator().geocode(query)
    except (GeocoderTimedOut, GeocoderServiceError, OSError) as exc:
        LOGGER.warning("Geocoding failed for %r: %s", query, exc)
        return None

    if not isinstance(location, Location):
        return None

    return Coordinates(latitude=float(location.latitude), longitude=float(location.longitude))


async def _lookup_with_rate_limit(query: str) -> Coordinates | None:
    """Geocode after the Nominatim courtesy delay, off the event loop.

    Args:
        query: Free-text place query.

    Returns:
        Coordinates on success, or None on failure.
    """
    await asyncio.sleep(NOMINATIM_REQUEST_DELAY_SECONDS)
    return await asyncio.to_thread(_lookup_coordinates, query)


async def geocode_alert_location(alert: FoodRecallAlertCreate) -> Coordinates:
    """Resolve one representative map pin for an alert via Nominatim.

    Uses affected regions when present (averaging multiple), falling back to
    country lookup and then static country centroids. Always applies jitter.

    Args:
        alert: Alert create payload with country and optional regions.

    Returns:
        Jittered Coordinates suitable for map display.
    """
    regions = cleaned_affected_regions(alert)
    country_query = country_geocode_query(alert)

    if len(regions) == 0:
        looked_up = await _lookup_with_rate_limit(country_query)
        base_coordinates = looked_up if looked_up is not None else fallback_coordinates(alert)
        return apply_coordinate_jitter(base_coordinates)

    if len(regions) == 1:
        query = region_geocode_query(regions[0], alert.country_source)
        looked_up = await _lookup_with_rate_limit(query)
        if looked_up is None:
            looked_up = await _lookup_with_rate_limit(country_query)
        base_coordinates = looked_up if looked_up is not None else fallback_coordinates(alert)
        return apply_coordinate_jitter(base_coordinates)

    region_coordinates: list[Coordinates] = []
    for region in regions:
        query = region_geocode_query(region, alert.country_source)
        looked_up = await _lookup_with_rate_limit(query)
        if looked_up is not None:
            region_coordinates.append(looked_up)

    if region_coordinates:
        base_coordinates = average_coordinates(region_coordinates)
    else:
        looked_up = await _lookup_with_rate_limit(country_query)
        base_coordinates = looked_up if looked_up is not None else fallback_coordinates(alert)

    return apply_coordinate_jitter(base_coordinates)
