"""Recall publication date candidate extraction and selection.

Wraps adaptive date parsing and applies recall-specific heuristics to pick the
most trustworthy publication date within a configurable lookback window.
"""

from datetime import UTC, date, datetime, timedelta
from typing import Iterable, Mapping

from agents.fetchers.extraction.date_parser import search_adaptive_dates

# Context phrases that disqualify nearby dates (e.g. expiry or filter UI dates).
DEFAULT_EXCLUDED_DATE_CONTEXT_MARKERS: tuple[str, ...] = (
    "last modified",
    "best before",
    "use by",
    "mindesthaltbar",
    "mhd",
    "prev :",
    "prev:",
    "previous :",
    "previous:",
    "next :",
    "next:",
    "last 24 hours",
    "last 7 days",
    "last 4 weeks",
    "last 6 months",
    "letzte 24 stunden",
    "letzte 7 tage",
    "letzte 4 wochen",
    "letzte 6 monate",
    "time period",
    "zeitraum",
    "detailed time period",
)

# Lower rank values indicate higher trust (structured > selector > generic).
_SOURCE_RANK: dict[str, int] = {
    "structured": 0,
    "selector": 1,
    "generic": 2,
}


def extract_date_candidates(
    text: str,
    *,
    languages: Iterable[str] | None = None,
    excluded_context_markers: Iterable[str] | None = DEFAULT_EXCLUDED_DATE_CONTEXT_MARKERS,
    reference_date: datetime | None = None,
) -> list[str]:
    """Find ISO-formatted publication date candidates in free text.

    Args:
        text: Page or snippet text to scan for dates.
        languages: Optional BCP 47 language hints passed to the date parser.
        excluded_context_markers: Substrings that disqualify dates appearing
            nearby in the source text.
        reference_date: Reference "now" for plausibility checks; defaults to UTC now.

    Returns:
        Unique ISO 8601 calendar dates (``YYYY-MM-DD``) in discovery order.
    """
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
    candidate_sources: Mapping[str, str] | None = None,
) -> str | None:
    """Pick a publication date within the lookback window.

    Prefer higher-trust sources (structured > selector > generic) and earlier
    document order over the chronologically latest candidate. Picking "latest"
    incorrectly favors UI chrome dates such as "today" on listing pages.

    Args:
        candidates: ISO date strings to evaluate.
        lookback_days: Maximum age in days relative to ``now``.
        now: Reference datetime; defaults to UTC now.
        candidate_sources: Optional mapping from candidate date to source label
            (``structured``, ``selector``, or ``generic``).

    Returns:
        The selected ISO date string, or ``None`` if no candidate qualifies.
    """
    current = now or datetime.now(tz=UTC)
    return _select_recall_date(
        candidates,
        current=current,
        oldest_allowed=current.date() - timedelta(days=lookback_days),
        candidate_sources=candidate_sources,
    )


def select_non_future_recall_date(
    candidates: Iterable[str],
    *,
    now: datetime | None = None,
    candidate_sources: Mapping[str, str] | None = None,
) -> str | None:
    """Pick the best publication date without applying a lookback window.

    Args:
        candidates: ISO date strings to evaluate.
        now: Reference datetime; defaults to UTC now.
        candidate_sources: Optional mapping from candidate date to source label.

    Returns:
        The selected ISO date string, or ``None`` if no candidate qualifies.
    """
    current = now or datetime.now(tz=UTC)
    return _select_recall_date(
        candidates,
        current=current,
        oldest_allowed=None,
        candidate_sources=candidate_sources,
    )


def _select_recall_date(
    candidates: Iterable[str],
    *,
    current: datetime,
    oldest_allowed: date | None,
    candidate_sources: Mapping[str, str] | None,
) -> str | None:
    """Score and rank recall date candidates by source trust and document order."""
    sources = candidate_sources or {}

    scored: list[tuple[int, int, str]] = []
    for index, candidate in enumerate(candidates):
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            continue
        if oldest_allowed is not None and parsed.date() < oldest_allowed:
            continue
        if parsed.date() > current.date():
            continue
        source_name = str(sources.get(candidate, "generic"))
        scored.append((_SOURCE_RANK.get(source_name, 2), index, parsed.date().isoformat()))

    if not scored:
        return None
    scored.sort(key=lambda item: (item[0], item[1]))
    return scored[0][2]
