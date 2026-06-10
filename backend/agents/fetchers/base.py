from __future__ import annotations

import logging
from typing import Any

import httpx

from agents.config import API_SOURCES
from agents.source_types import SourceRecord

LOGGER = logging.getLogger(__name__)

SOURCE_REQUEST_HEADERS = {
    "Accept": "application/json,text/plain,*/*",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36"
    ),
}


async def fetch_source_records(
    source: str,
    *,
    limit: int,
    client: httpx.AsyncClient,
) -> list[SourceRecord]:
    response = await client.get(API_SOURCES[source])
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
) -> list[SourceRecord]:
    records: list[SourceRecord] = []
    async with httpx.AsyncClient(timeout=30.0, headers=SOURCE_REQUEST_HEADERS) as client:
        for source in sources:
            try:
                records.extend(
                    await fetch_source_records(source, limit=limit, client=client)
                )
            except (KeyError, httpx.HTTPError, ValueError) as exc:
                LOGGER.warning("Skipping %s recall source after fetch failure: %s", source, exc)
    return records
