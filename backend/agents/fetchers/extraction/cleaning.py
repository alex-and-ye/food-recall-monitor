"""Sanitize extracted recall detail payloads before downstream processing.

Strips HTML, removes boilerplate text, canonicalizes source URLs, and validates
that cleaned fields contain no remaining markup.
"""

import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup

# URL query parameter prefixes removed during canonicalization.
TRACKING_QUERY_PREFIXES = ("utm_", "fbclid", "gclid", "mc_", "ref")
# Footer and navigation phrases filtered from visible text.
BOILERPLATE_MARKERS = (
    "cookie",
    "privacy policy",
    "terms and conditions",
    "accessibility",
    "newsletter",
    "all rights reserved",
)

# Detects HTML tags that should not remain after cleaning.
HTML_TAG_RE = re.compile(r"<[^>]+>")
# Collapses repeated whitespace in plain text.
MULTISPACE_RE = re.compile(r"\s+")


def clean_detail_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize headings, visible text, and source URL in a detail payload.

    Args:
        payload: Raw extraction result containing ``headings``, ``visible_text``,
            ``source_url``, and optional recall date fields.

    Returns:
        A cleaned copy of the payload with HTML removed, boilerplate filtered,
        and the source URL canonicalized.

    Raises:
        ValueError: If HTML tags remain in ``visible_text`` or ``headings`` after
            cleaning.
    """
    headings = [
        _normalize_plain_text(_strip_html(str(heading)))
        for heading in payload.get("headings", [])
        if str(heading).strip()
    ]
    headings = [heading for heading in headings if heading]
    visible_text = _clean_visible_text(str(payload.get("visible_text", "")))
    source_url = _canonicalize_url(str(payload.get("source_url", "")))

    cleaned = {
        "source_url": source_url,
        "headings": headings,
        "visible_text": visible_text,
    }

    selected_date = payload.get("selected_recall_date")
    if isinstance(selected_date, str) and selected_date.strip():
        cleaned["selected_recall_date"] = selected_date.strip()
    selected_date_source = payload.get("selected_recall_date_source")
    if isinstance(selected_date_source, str) and selected_date_source.strip():
        cleaned["selected_recall_date_source"] = selected_date_source.strip()

    _assert_no_html_tags(cleaned)
    return cleaned


def _strip_html(value: str) -> str:
    """Convert an HTML fragment to plain text."""
    if not value.strip():
        return ""
    return BeautifulSoup(value, "html.parser").get_text(" ", strip=True)


def _clean_visible_text(value: str) -> str:
    """Strip HTML and remove boilerplate sentences from page body text."""
    plain = _normalize_plain_text(_strip_html(value))
    if not plain:
        return ""

    lines = [chunk.strip() for chunk in plain.split(". ")]
    filtered = [
        line
        for line in lines
        if line
        and not any(marker in line.lower() for marker in BOILERPLATE_MARKERS)
    ]
    return ". ".join(filtered).strip()


def _normalize_plain_text(value: str) -> str:
    """Collapse whitespace and trim surrounding space."""
    return MULTISPACE_RE.sub(" ", value).strip()


def _canonicalize_url(url: str) -> str:
    """Remove tracking query parameters and URL fragments."""
    if not url.strip():
        return ""

    parts = urlsplit(url)
    filtered_query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not any(key.lower().startswith(prefix) for prefix in TRACKING_QUERY_PREFIXES)
    ]
    clean_query = urlencode(filtered_query, doseq=True)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, clean_query, ""))


def _assert_no_html_tags(cleaned_payload: dict[str, Any]) -> None:
    """Raise if any cleaned text field still contains HTML markup."""
    if HTML_TAG_RE.search(str(cleaned_payload.get("visible_text", ""))):
        raise ValueError("Unexpected HTML tags after cleaning: visible_text")
    for heading in cleaned_payload.get("headings", []):
        if HTML_TAG_RE.search(str(heading)):
            raise ValueError("Unexpected HTML tags after cleaning: headings")
