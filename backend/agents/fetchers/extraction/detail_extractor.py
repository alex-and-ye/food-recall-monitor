from __future__ import annotations

import json
import re
from typing import Any, Iterable

from bs4 import BeautifulSoup
from bs4.element import Tag

from agents.fetchers.extraction.date_candidates import extract_date_candidates
from agents.fetchers.extraction.date_parser import (
    extract_structured_dates,
    infer_document_languages,
)

_PUBLISHED_META_KEYS = frozenset(
    {
        "article:published_time",
        "og:published_time",
        "publish-date",
        "pubdate",
        "publication_date",
        "date",
        "dc.date",
        "dc.date.issued",
        "sailthru.date",
    }
)
_JSON_LD_DATE_KEYS = frozenset(
    {
        "datepublished",
        "datecreated",
        "uploaddate",
    }
)


def extract_detail_payload(
    *,
    source_url: str,
    html: str,
    date_selectors: list[str] | None = None,
    date_languages: Iterable[str] | None = None,
) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    content_root = _content_root(soup)
    document_languages = infer_document_languages(
        _html_language(soup),
        configured_languages=date_languages,
    )
    heading_tags = content_root.find_all(["h1", "h2", "h3"])
    visible_text = content_root.get_text(" ", strip=True)

    extra_date_text: list[str] = []
    structured_date_values: list[str] = []
    for selector in date_selectors or []:
        for node in content_root.select(selector):
            extracted = node.get_text(" ", strip=True)
            if extracted:
                extra_date_text.append(extracted)
            structured_date_values.extend(_datetime_attribute_values(node))

    structured_date_values.extend(_structured_dates_in_document(soup, content_root))
    extra_date_text.extend(_time_element_texts(content_root))
    structured_candidates = extract_structured_dates(structured_date_values)
    # Parse each selector/time node separately so adjacent dates cannot form
    # false fragments like "2026 07" that dateparser fills with today's day.
    selector_candidates: list[str] = []
    for date_text in extra_date_text:
        selector_candidates.extend(
            extract_date_candidates(
                date_text,
                languages=document_languages,
            )
        )
    selector_candidates = _merge_date_candidates(selector_candidates)
    generic_candidates = extract_date_candidates(
        visible_text,
        languages=document_languages,
    )
    date_candidates = _merge_date_candidates(
        structured_candidates,
        selector_candidates,
        generic_candidates,
    )

    return {
        "source_url": source_url,
        "headings": [str(tag) for tag in heading_tags[:8]],
        "visible_text": visible_text,
        "published_date_candidates": date_candidates,
        "published_date_candidate_sources": _date_candidate_sources(
            structured_candidates,
            selector_candidates,
            generic_candidates,
        ),
    }


def _html_language(soup: BeautifulSoup) -> str | None:
    html_tag = soup.find("html")
    if html_tag is None:
        return None
    lang = html_tag.get("lang")
    return str(lang).strip() if lang else None


def _content_root(soup: BeautifulSoup) -> Tag:
    main_tag = soup.select_one("body main") or soup.find("main")
    if main_tag is not None:
        return main_tag
    if soup.body is not None:
        return soup.body
    return soup


def _datetime_attribute_values(node: Tag) -> list[str]:
    values: list[str] = []
    for attribute in ("datetime", "content", "data-date", "data-published", "data-datetime"):
        raw_value = node.get(attribute)
        if raw_value:
            values.append(str(raw_value))
    return values


def _structured_dates_in_document(soup: BeautifulSoup, content_root: Tag) -> list[str]:
    values: list[str] = []
    for node in content_root.select("[datetime]"):
        values.extend(_datetime_attribute_values(node))
    for tag in soup.find_all("meta"):
        key = str(tag.get("property") or tag.get("name") or "").strip().lower()
        if key not in _PUBLISHED_META_KEYS:
            continue
        content = tag.get("content")
        if content:
            values.append(str(content))
    for script in soup.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)}):
        raw = script.string or script.get_text() or ""
        values.extend(_json_ld_date_values(raw))
    return values


def _time_element_texts(content_root: Tag) -> list[str]:
    """Collect <time> body text when pages omit a machine-readable datetime attr."""
    values: list[str] = []
    for node in content_root.find_all("time"):
        text = node.get_text(" ", strip=True)
        if text:
            values.append(text)
    return values


def _json_ld_date_values(raw: str) -> list[str]:
    text = raw.strip()
    if not text:
        return []
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return []
    values: list[str] = []
    _collect_json_ld_dates(payload, values)
    return values


def _collect_json_ld_dates(node: object, values: list[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if str(key).strip().lower() in _JSON_LD_DATE_KEYS and isinstance(value, str):
                if value.strip():
                    values.append(value.strip())
            else:
                _collect_json_ld_dates(value, values)
    elif isinstance(node, list):
        for item in node:
            _collect_json_ld_dates(item, values)


def _merge_date_candidates(*candidate_groups: list[str]) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for candidates in candidate_groups:
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            merged.append(candidate)
    return merged


def _date_candidate_sources(
    structured_candidates: list[str],
    selector_candidates: list[str],
    generic_candidates: list[str],
) -> dict[str, str]:
    sources: dict[str, str] = {}
    for candidate in structured_candidates:
        sources.setdefault(candidate, "structured")
    for candidate in selector_candidates:
        sources.setdefault(candidate, "selector")
    for candidate in generic_candidates:
        sources.setdefault(candidate, "generic")
    return sources
