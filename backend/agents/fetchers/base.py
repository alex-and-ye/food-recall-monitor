from __future__ import annotations

import httpx

from agents.source_types import SourceRecord
from models.pipeline_options import RecallSource


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
    async with httpx.AsyncClient(timeout=30.0) as client:
        for source in sources:
            records.extend(
                await fetch_source_records(source, limit=limit, client=client)
            )
    return records
