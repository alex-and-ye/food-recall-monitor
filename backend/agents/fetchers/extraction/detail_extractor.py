from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup
from bs4.element import Tag

from agents.fetchers.extraction.date_candidates import extract_date_candidates


def extract_detail_payload(
    *,
    source_url: str,
    html: str,
    date_selectors: list[str] | None = None,
) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    content_root = _content_root(soup)
    title_tag = content_root.find("h1") or soup.find("title")
    heading_tags = content_root.find_all(["h1", "h2", "h3"])
    visible_text = content_root.get_text(" ", strip=True)

    extra_date_text: list[str] = []
    for selector in date_selectors or []:
        for node in content_root.select(selector):
            extracted = node.get_text(" ", strip=True)
            if extracted:
                extra_date_text.append(extracted)

    selector_candidates = extract_date_candidates(
        " ".join(extra_date_text),
        excluded_context_markers=(),
    )
    generic_candidates = extract_date_candidates(visible_text)
    date_candidates = _merge_date_candidates(selector_candidates, generic_candidates)

    return {
        "source_url": source_url,
        "title": str(title_tag) if title_tag else "",
        "headings": [str(tag) for tag in heading_tags[:8]],
        "visible_text": visible_text,
        "published_date_candidates": date_candidates,
        "published_date_candidate_sources": _date_candidate_sources(
            selector_candidates,
            generic_candidates,
        ),
    }


def _content_root(soup: BeautifulSoup) -> Tag:
    main_tag = soup.select_one("body main") or soup.find("main")
    if main_tag is not None:
        return main_tag
    if soup.body is not None:
        return soup.body
    return soup


def _merge_date_candidates(selector_candidates: list[str], generic_candidates: list[str]) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for candidate in [*selector_candidates, *generic_candidates]:
        if candidate in seen:
            continue
        seen.add(candidate)
        merged.append(candidate)
    return merged


def _date_candidate_sources(selector_candidates: list[str], generic_candidates: list[str]) -> dict[str, str]:
    sources: dict[str, str] = {}
    for candidate in selector_candidates:
        sources.setdefault(candidate, "selector")
    for candidate in generic_candidates:
        sources.setdefault(candidate, "generic")
    return sources
