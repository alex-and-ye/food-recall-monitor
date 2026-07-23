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
ISO_DATE_PATTERN = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
COMPLETE_NUMERIC_DATE_PATTERN = re.compile(r"^\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}$")
COMPLETE_ISO_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
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
        as_date = _calendar_date(parsed)
        if not _is_plausible_recall_date(as_date, reference=current.date()):
            return
        if as_date in seen:
            return
        seen.add(as_date)
        candidates.append(as_date)

    base_settings = {
        "RETURN_AS_TIMEZONE_AWARE": True,
        "PREFER_DATES_FROM": "past",
        "STRICT_PARSING": True,
    }

    for date_order in DATE_ORDERS:
        settings = {**base_settings, "DATE_ORDER": date_order}
        matches = search_dates(text, languages=language_list or None, settings=settings)
        if not matches:
            continue
        for matched_text, parsed in matches:
            if not _is_complete_date_match(matched_text):
                continue
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

    for matched_text in _unique_matches(ISO_DATE_PATTERN.findall(text)):
        try:
            parsed = datetime.fromisoformat(matched_text).replace(tzinfo=UTC)
        except ValueError:
            continue
        _add_candidate(parsed, matched_text)

    return candidates


def extract_structured_dates(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    candidates: list[str] = []
    for raw_value in values:
        for normalized in _normalize_structured_date_values(raw_value):
            if normalized in seen:
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


def _normalize_structured_date_values(value: str) -> list[str]:
    text = value.strip()
    if not text:
        return []

    iso_text = text
    if iso_text.endswith("Z"):
        iso_text = f"{iso_text[:-1]}+00:00"

    try:
        parsed = datetime.fromisoformat(iso_text)
    except ValueError:
        parsed = None

    if parsed is not None:
        as_date = _calendar_date(parsed)
        if _is_plausible_recall_date(as_date):
            return [as_date]
        return []

    # Isolated numeric attributes: dotted values are almost always DMY on recall portals.
    # Slash-separated values stay ambiguous across locales.
    if COMPLETE_NUMERIC_DATE_PATTERN.fullmatch(text):
        orders = ("DMY",) if "." in text else DATE_ORDERS
        seen: set[str] = set()
        candidates: list[str] = []
        base_settings = {
            "RETURN_AS_TIMEZONE_AWARE": True,
            "PREFER_DATES_FROM": "past",
            "STRICT_PARSING": True,
        }
        for date_order in orders:
            parsed_value = parse_date(
                text,
                settings={**base_settings, "DATE_ORDER": date_order},
            )
            if parsed_value is None:
                continue
            as_date = _calendar_date(parsed_value)
            if not _is_plausible_recall_date(as_date) or as_date in seen:
                continue
            seen.add(as_date)
            candidates.append(as_date)
        return candidates

    # Named months and other non-ISO attributes.
    return search_adaptive_dates(text)


def _calendar_date(parsed: datetime) -> str:
    """Preserve the source's calendar date instead of shifting it through UTC.

    Recall publication values represent civil dates. Converting a timezone-less
    evening timestamp (or an offset timestamp near midnight) can change the day.
    """
    return parsed.date().isoformat()


def _is_complete_date_match(matched_text: str) -> bool:
    """Reject incomplete fragments like '2026 07' that borrow today's day."""
    text = matched_text.strip()
    if not text:
        return False
    if COMPLETE_NUMERIC_DATE_PATTERN.fullmatch(text) or COMPLETE_ISO_DATE_PATTERN.fullmatch(text):
        return True
    # Named months such as "4 June 2026" / "July 10, 2026".
    if re.search(r"[A-Za-zÀ-ÿ]{3,}", text) and re.search(r"\d{4}", text):
        return True
    digit_groups = re.findall(r"\d+", text)
    return len(digit_groups) >= 3


def _is_plausible_recall_date(value: str, *, reference: date | None = None) -> bool:
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return False

    current = reference or datetime.now(tz=UTC).date()
    return date(1900, 1, 1) <= parsed <= current


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
