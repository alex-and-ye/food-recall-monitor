from __future__ import annotations

import html
import re
from datetime import date, datetime
from typing import Any

from agents.source_types import ProtectedFields


_HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
_WHITESPACE_PATTERN = re.compile(r"\s+")


def first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return clean_text(value)
    return ""


def clean_text(value: str) -> str:
    unescaped = html.unescape(value)
    without_tags = _HTML_TAG_PATTERN.sub(" ", unescaped)
    return _WHITESPACE_PATTERN.sub(" ", without_tags).strip()


def split_source_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [clean_text(str(item)) for item in value if str(item).strip()]
    if isinstance(value, str):
        return [
            clean_text(item)
            for item in value.replace("\u00a4", "|").split("|")
            if item.strip()
        ]
    return [clean_text(str(value))]


def parse_source_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Missing recall date")

    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"

    try:
        return datetime.fromisoformat(normalized).date()
    except ValueError:
        return date.fromisoformat(normalized[:10])


def build_protected_fields(
    *,
    product_name: str,
    recall_date: Any,
    source_url: str,
) -> ProtectedFields:
    clean_product_name = clean_text(product_name)
    clean_source_url = source_url.strip()
    if not clean_product_name:
        raise ValueError("Missing product_name")
    if not clean_source_url:
        raise ValueError("Missing source_url")

    return ProtectedFields(
        product_name=clean_product_name,
        recall_date=parse_source_date(recall_date),
        source_url=clean_source_url,
    )
