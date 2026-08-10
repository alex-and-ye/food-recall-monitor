"""Normalization helpers for protected recall source fields.

Cleans text values and parses recall publication dates from heterogeneous
upstream formats.
"""

import html
import re
from datetime import date, datetime
from typing import Any

# Removes HTML tags from normalized text values.
_HTML_TAG_PATTERN: re.Pattern[str] = re.compile(r"<[^>]+>")
# Collapses repeated whitespace after tag removal.
_WHITESPACE_PATTERN: re.Pattern[str] = re.compile(r"\s+")


def clean_text(value: str) -> str:
    """Unescape HTML entities, strip tags, and normalize whitespace.

    Args:
        value: Raw text that may contain HTML markup or entities.

    Returns:
        Plain text with collapsed whitespace.
    """
    unescaped = html.unescape(value)
    without_tags = _HTML_TAG_PATTERN.sub(" ", unescaped)
    return _WHITESPACE_PATTERN.sub(" ", without_tags).strip()


def parse_source_date(value: Any) -> date:
    """Parse a recall publication date from common upstream representations.

    Args:
        value: A ``date``, ``datetime``, or ISO date/datetime string.

    Returns:
        The parsed calendar date.

    Raises:
        ValueError: If ``value`` is missing or cannot be parsed as a date.
    """
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
