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


def parse_uk_payload(payload: dict[str, Any], *, limit: int) -> list[SourceRecord]:
    records = payload.get("items", [])
    parsed: list[SourceRecord] = []

    for raw_record in records[:limit]:
        if not isinstance(raw_record, dict):
            continue

        try:
            parsed.append(_build_uk_record(raw_record))
        except ValueError:
            continue

    return parsed


async def fetch_uk_records(
    *,
    limit: int,
    client: httpx.AsyncClient,
) -> list[SourceRecord]:
    response = await client.get(SOURCE_URLS[RecallSource.UK])
    response.raise_for_status()
    return parse_uk_payload(response.json(), limit=limit)


def _build_uk_record(raw_record: dict[str, Any]) -> SourceRecord:
    product_name = first_text(
        _first_product_detail(raw_record, "productName"),
        raw_record.get("shortTitle"),
        raw_record.get("title"),
    )

    protected_fields = build_protected_fields(
        product_name=product_name,
        recall_date=raw_record.get("created"),
        source_url=first_text(raw_record.get("alertURL"), raw_record.get("@id")),
    )

    working_json = {
        "source": RecallSource.UK.value,
        "title": first_text(raw_record.get("title")),
        "description": first_text(raw_record.get("description")),
        "reporting_business": _nested_text(raw_record, "reportingBusiness", "commonName"),
        "product_details": {
            "pack_size": _first_product_detail(raw_record, "packSizeDescription"),
            "batch_details": _batch_descriptions(raw_record),
        },
        "recall_reason": _problem_text(raw_record),
        "risk_details": _problem_text(raw_record),
        "consumer_action": first_text(
            raw_record.get("consumerAdvice"),
            raw_record.get("actionTaken"),
        ),
        "affected_regions": _country_labels(raw_record),
        "status": _nested_text(raw_record, "status", "label"),
    }

    return SourceRecord(
        source=RecallSource.UK,
        raw_record=raw_record,
        protected_fields=protected_fields,
        working_json=working_json,
    )


def _first_product_detail(raw_record: dict[str, Any], key: str) -> str:
    product_details = raw_record.get("productDetails")
    if not isinstance(product_details, list):
        return ""

    for item in product_details:
        if isinstance(item, dict):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return clean_text(value)
    return ""


def _batch_descriptions(raw_record: dict[str, Any]) -> list[str]:
    descriptions: list[str] = []
    product_details = raw_record.get("productDetails")
    if not isinstance(product_details, list):
        return descriptions

    for product in product_details:
        if not isinstance(product, dict):
            continue
        batches = product.get("batchDescription")
        if not isinstance(batches, list):
            continue
        for batch in batches:
            if isinstance(batch, dict):
                description = first_text(batch.get("bestBeforeDescription"))
                if description:
                    descriptions.append(description)
    return descriptions


def _problem_text(raw_record: dict[str, Any]) -> str:
    problem = raw_record.get("problem")
    if not isinstance(problem, list):
        return ""

    statements = [
        first_text(item.get("riskStatement"))
        for item in problem
        if isinstance(item, dict)
    ]
    return " ".join(statement for statement in statements if statement)


def _country_labels(raw_record: dict[str, Any]) -> list[str]:
    countries = raw_record.get("country")
    if not isinstance(countries, list):
        return []

    labels: list[str] = []
    for country in countries:
        if not isinstance(country, dict):
            continue
        label = country.get("label")
        if isinstance(label, list):
            labels.extend(clean_text(str(item)) for item in label if str(item).strip())
        elif isinstance(label, str) and label.strip():
            labels.append(clean_text(label))

    return sorted(set(labels))


def _nested_text(raw_record: dict[str, Any], parent: str, key: str) -> str:
    value = raw_record.get(parent)
    if isinstance(value, dict):
        return first_text(value.get(key))
    return ""
