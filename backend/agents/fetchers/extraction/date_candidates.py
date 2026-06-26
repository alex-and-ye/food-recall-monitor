from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Iterable

from dateparser.search import search_dates


DEFAULT_EXCLUDED_DATE_CONTEXT_MARKERS: tuple[str, ...] = (
    "last modified",
    "best before",
    "prev :",
    "prev:",
    "previous :",
    "previous:",
    "next :",
    "next:",
)


def extract_date_candidates(
    text: str,
    *,
    excluded_context_markers: Iterable[str] | None = DEFAULT_EXCLUDED_DATE_CONTEXT_MARKERS,
) -> list[str]:
    if not text.strip():
        return []

    matches = search_dates(
        text,
        settings={
            "RETURN_AS_TIMEZONE_AWARE": True,
            "PREFER_DATES_FROM": "past",
        },
    )
    if not matches:
        return []

    seen: set[str] = set()
    candidates: list[str] = []
    markers = tuple(marker.lower() for marker in excluded_context_markers or ())
    for matched_text, parsed in matches:
        if _is_excluded_date_context(text, matched_text, markers):
            continue
        as_date = parsed.astimezone(UTC).date().isoformat()
        if as_date not in seen:
            seen.add(as_date)
            candidates.append(as_date)
    return candidates


def _is_excluded_date_context(text: str, matched_text: str, markers: tuple[str, ...]) -> bool:
    if not markers:
        return False

    lowered_text = text.lower()
    matched_index = lowered_text.find(matched_text.lower())
    if matched_index < 0:
        return False

    context_start = max(0, matched_index - 80)
    context = lowered_text[context_start : matched_index + len(matched_text)]
    return any(marker in context for marker in markers)


def select_recent_recall_date(
    candidates: Iterable[str],
    *,
    lookback_days: int,
    now: datetime | None = None,
) -> str | None:
    current = now or datetime.now(tz=UTC)
    oldest_allowed = current.date() - timedelta(days=lookback_days)
    latest: datetime | None = None

    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            continue
        if parsed.date() < oldest_allowed:
            continue
        if parsed.date() > current.date():
            continue
        if latest is None or parsed > latest:
            latest = parsed

    if latest is None:
        return None
    return latest.date().isoformat()
