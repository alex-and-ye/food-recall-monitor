from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import httpx

from agents.config import API_SOURCES
from agents.source_types import SourceRecord
from models.pipeline_result import FetchSourcesResult

LOGGER = logging.getLogger(__name__)

SOURCE_REQUEST_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
}


def _headers_for_source(source: str) -> dict[str, str]:
    headers = dict(SOURCE_REQUEST_HEADERS)
    headers.update(_source_headers(API_SOURCES[source]))
    return headers


def _source_url(source: str) -> str:
    source_config = API_SOURCES[source]
    if isinstance(source_config, str):
        return source_config
    if isinstance(source_config, Mapping):
        return str(source_config["url"])
    raise ValueError(f"Invalid API source config for {source}")


def _source_headers(source_config: object) -> dict[str, str]:
    if not isinstance(source_config, Mapping):
        return {}

    headers = source_config.get("headers", {})
    if not isinstance(headers, Mapping):
        raise ValueError("API source headers must be a mapping")

    return {
        str(key): str(value)
        for key, value in headers.items()
    }


async def fetch_source_records(
    source: str,
    *,
    limit: int,
    client: httpx.AsyncClient,
) -> list[SourceRecord]:
    response = await client.get(_source_url(source), headers=_headers_for_source(source))
    response.raise_for_status()
    return parse_source_payload(source, response.json(), limit=limit)


def parse_source_payload(
    source: str,
    payload: Any,
    *,
    limit: int,
) -> list[SourceRecord]:
    return [
        SourceRecord(
            source=source,
            raw_record=raw_record,
            working_json={
                "source": source,
                "record": raw_record,
            },
        )
        for raw_record in _infer_records(payload)[:limit]
        if isinstance(raw_record, dict)
    ]


def _infer_records(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []

    for key in ("results", "items", "data", "records"):
        value = payload.get(key)
        if _is_record_list(value):
            return value

    lists = _collect_record_lists(payload)
    if not lists:
        return [payload]

    return max(lists, key=len)


def _collect_record_lists(value: Any) -> list[list[Any]]:
    if isinstance(value, list):
        return [value] if _is_record_list(value) else []
    if isinstance(value, dict):
        lists: list[list[Any]] = []
        for child in value.values():
            lists.extend(_collect_record_lists(child))
        return lists
    return []


def _is_record_list(value: Any) -> bool:
    return isinstance(value, list) and any(isinstance(item, dict) for item in value)


async def fetch_sources_sequentially(
    sources: list[str],
    *,
    limit: int,
) -> FetchSourcesResult:
    records: list[SourceRecord] = []
    failures: dict[str, str] = {}
    async with httpx.AsyncClient(timeout=30.0, headers=SOURCE_REQUEST_HEADERS) as client:
        for source in sources:
            try:
                records.extend(
                    await fetch_source_records(source, limit=limit, client=client)
                )
            except (KeyError, httpx.HTTPError, ValueError) as exc:
                failures[source] = str(exc)
                LOGGER.warning("Skipping %s recall source after fetch failure: %s", source, exc)
    return FetchSourcesResult(records=records, failures=failures)
