from __future__ import annotations

import asyncio
import logging
import random
from typing import NamedTuple

from geopy.exc import GeocoderServiceError, GeocoderTimedOut
from geopy.geocoders import Nominatim
from geopy.location import Location

from models.food_recall_alert import CountrySource, FoodRecallAlertCreate

LOGGER: logging.Logger = logging.getLogger(__name__)

NOMINATIM_REQUEST_DELAY_SECONDS: float = 1.5
COORDINATE_JITTER_DEGREES: float = 0.1

COUNTRY_CENTER_COORDINATES: dict[str, tuple[float, float]] = {
    CountrySource.FRANCE: (46.2276, 2.2137),
    CountrySource.GERMANY: (51.1657, 10.4515),
    CountrySource.UK: (55.3781, -3.4360),
    "United Kingdom": (55.3781, -3.4360),
}

class Coordinates(NamedTuple):
    latitude: float
    longitude: float

_geolocator: Nominatim | None = None

def _get_geolocator() -> Nominatim:
    global _geolocator
    if _geolocator is None:
        _geolocator = Nominatim(user_agent="food-recall-monitor")
    return _geolocator

def cleaned_affected_regions(alert: FoodRecallAlertCreate) -> list[str]:
    regions: list[str] = []
    for region in alert.affected_regions:
        cleaned = region.strip()
        if cleaned:
            regions.append(cleaned)
    return regions

def country_geocode_query(alert: FoodRecallAlertCreate) -> str:
    return alert.country_source.strip()

def region_geocode_query(region: str, country_source: str) -> str:
    country = country_source.strip()
    if country:
        return f"{region}, {country}"
    return region

def fallback_coordinates(alert: FoodRecallAlertCreate) -> Coordinates:
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
    await asyncio.sleep(NOMINATIM_REQUEST_DELAY_SECONDS)
    return await asyncio.to_thread(_lookup_coordinates, query)

async def geocode_alert_location(alert: FoodRecallAlertCreate) -> Coordinates:
    """Resolve one representative map pin for an alert via Nominatim."""
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
