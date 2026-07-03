from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Iterable

from agents.fetchers.extraction.date_parser import search_adaptive_dates

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
    languages: Iterable[str] | None = None,
    excluded_context_markers: Iterable[str] | None = DEFAULT_EXCLUDED_DATE_CONTEXT_MARKERS,
    reference_date: datetime | None = None,
) -> list[str]:
    return search_adaptive_dates(
        text,
        languages=languages,
        excluded_context_markers=excluded_context_markers,
        reference_date=reference_date,
    )


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
