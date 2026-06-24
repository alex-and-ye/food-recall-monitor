from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Iterable

from dateparser.search import search_dates


def extract_date_candidates(text: str) -> list[str]:
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
    for _, parsed in matches:
        as_date = parsed.astimezone(UTC).date().isoformat()
        if as_date not in seen:
            seen.add(as_date)
            candidates.append(as_date)
    return candidates


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
