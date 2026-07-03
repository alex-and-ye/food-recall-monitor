from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import Iterable

from dateparser import parse as parse_date
from dateparser.search import search_dates

DATE_ORDERS: tuple[str, ...] = ("DMY", "MDY", "YMD")
NUMERIC_DATE_PATTERN = re.compile(
    r"\b(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})\b",
)
HTML_LANG_PATTERN = re.compile(r"^[a-z]{2}")


def infer_document_languages(
    html_lang: str | None,
    *,
    configured_languages: Iterable[str] | None = None,
) -> list[str]:
    languages: list[str] = []
    seen: set[str] = set()

    for raw_language in configured_languages or ():
        normalized = _normalize_language_code(str(raw_language))
        if normalized and normalized not in seen:
            seen.add(normalized)
            languages.append(normalized)

    normalized_html_lang = _normalize_language_code(html_lang)
    if normalized_html_lang and normalized_html_lang not in seen:
        seen.add(normalized_html_lang)
        languages.insert(0, normalized_html_lang)

    return languages


def search_adaptive_dates(
    text: str,
    *,
    languages: Iterable[str] | None = None,
    excluded_context_markers: Iterable[str] | None = None,
    reference_date: datetime | None = None,
) -> list[str]:
    if not text.strip():
        return []

    language_list = list(languages or [])
    markers = tuple(marker.lower() for marker in excluded_context_markers or ())
    current = reference_date or datetime.now(tz=UTC)
    seen: set[str] = set()
    candidates: list[str] = []

    def _add_candidate(parsed: datetime, matched_text: str) -> None:
        if _is_excluded_date_context(text, matched_text, markers):
            return
        as_date = parsed.astimezone(UTC).date().isoformat()
        if not _is_plausible_recall_date(as_date, reference=current.date()):
            return
        if as_date in seen:
            return
        seen.add(as_date)
        candidates.append(as_date)

    base_settings = {
        "RETURN_AS_TIMEZONE_AWARE": True,
        "PREFER_DATES_FROM": "past",
        "STRICT_PARSING": False,
    }

    for date_order in DATE_ORDERS:
        settings = {**base_settings, "DATE_ORDER": date_order}
        matches = search_dates(text, languages=language_list or None, settings=settings)
        if not matches:
            continue
        for matched_text, parsed in matches:
            _add_candidate(parsed, matched_text)

    for matched_text in _unique_matches(NUMERIC_DATE_PATTERN.findall(text)):
        for date_order in DATE_ORDERS:
            parsed = parse_date(
                matched_text,
                languages=language_list or None,
                settings={**base_settings, "DATE_ORDER": date_order},
            )
            if parsed is not None:
                _add_candidate(parsed, matched_text)

    return candidates


def extract_structured_dates(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    candidates: list[str] = []
    for raw_value in values:
        normalized = _normalize_structured_date(raw_value)
        if normalized is None or normalized in seen:
            continue
        seen.add(normalized)
        candidates.append(normalized)
    return candidates


def _normalize_language_code(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower().replace("_", "-")
    if not normalized:
        return None
    match = HTML_LANG_PATTERN.match(normalized)
    return match.group(0) if match else None


def _normalize_structured_date(value: str) -> str | None:
    text = value.strip()
    if not text:
        return None

    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None

    as_date = parsed.astimezone(UTC).date().isoformat()
    if not _is_plausible_recall_date(as_date):
        return None
    return as_date


def _is_plausible_recall_date(value: str, *, reference: date | None = None) -> bool:
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return False

    current = reference or datetime.now(tz=UTC).date()
    return 1900 <= parsed.year <= current.year + 1


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


def _unique_matches(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered
