from __future__ import annotations

import logging

import httpx

from agents.source_types import SourceRecord
from models.pipeline_options import RecallSource

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
    source: RecallSource,
    *,
    limit: int,
    client: httpx.AsyncClient,
) -> list[SourceRecord]:
    from agents.fetchers.france import fetch_france_records
    from agents.fetchers.uk import fetch_uk_records
    from agents.fetchers.us import fetch_us_records

    fetchers = {
        RecallSource.FRANCE: fetch_france_records,
        RecallSource.UK: fetch_uk_records,
        RecallSource.US: fetch_us_records,
    }

    return await fetchers[source](limit=limit, client=client)


async def fetch_sources_sequentially(
    sources: list[RecallSource],
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
            except (httpx.HTTPError, ValueError) as exc:
                LOGGER.warning("Skipping %s recall source after fetch failure: %s", source.value, exc)
    return records
