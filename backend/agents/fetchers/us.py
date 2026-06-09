from __future__ import annotations

from typing import Any

import httpx

from agents.config import SOURCE_URLS
from agents.normalizers.protected_fields import (
    build_protected_fields,
    clean_text,
    first_text,
)
from agents.source_types import SourceRecord
from models.pipeline_options import RecallSource


def parse_us_payload(payload: Any, *, limit: int) -> list[SourceRecord]:
    records = _extract_records(payload)
    parsed: list[SourceRecord] = []

    for raw_record in records[:limit]:
        if not isinstance(raw_record, dict):
            continue

        try:
            parsed.append(_build_us_record(raw_record))
        except ValueError:
            continue

    return parsed


async def fetch_us_records(
    *,
    limit: int,
    client: httpx.AsyncClient,
) -> list[SourceRecord]:
    response = await client.get(SOURCE_URLS[RecallSource.US])
    response.raise_for_status()
    return parse_us_payload(response.json(), limit=limit)


def _build_us_record(raw_record: dict[str, Any]) -> SourceRecord:
    protected_fields = build_protected_fields(
        product_name=first_text(
            raw_record.get("field_title"),
            raw_record.get("field_product_items"),
            raw_record.get("field_establishment"),
        ),
        recall_date=raw_record.get("field_recall_date"),
        source_url=first_text(raw_record.get("field_recall_url")),
    )

    working_json = {
        "source": RecallSource.US.value,
        "title": first_text(raw_record.get("field_title")),
        "establishment": first_text(raw_record.get("field_establishment")),
        "product_category": first_text(raw_record.get("field_processing")),
        "product_details": first_text(raw_record.get("field_product_items")),
        "recall_reason": first_text(raw_record.get("field_recall_reason")),
        "risk_level": first_text(
            raw_record.get("field_risk_level"),
            raw_record.get("field_recall_classification"),
        ),
        "recall_type": first_text(raw_record.get("field_recall_type")),
        "summary": first_text(raw_record.get("field_summary")),
        "affected_regions": _state_regions(raw_record.get("field_states")),
        "quantity_recovered": first_text(raw_record.get("field_qty_recovered")),
        "related_to_outbreak": first_text(raw_record.get("field_related_to_outbreak")),
    }

    return SourceRecord(
        source=RecallSource.US,
        raw_record=raw_record,
        protected_fields=protected_fields,
        working_json=working_json,
    )


def _extract_records(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("results", "items", "data"):
            records = payload.get(key)
            if isinstance(records, list):
                return records
    return []


def _state_regions(value: Any) -> list[str]:
    if not isinstance(value, str) or not value.strip():
        return []

    normalized = value.replace(";", ",").replace("|", ",")
    return [
        clean_text(region)
        for region in normalized.split(",")
        if region.strip()
    ]
