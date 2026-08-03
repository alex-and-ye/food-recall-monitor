"""Fetch and normalize arbitrary discovery URLs for early-warning processing.

Attempts static HTML first, falls back to a browser for JS shells, extracts
detail payloads, and records provenance for Brave Search candidates.
"""

import hashlib
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

from agents.fetchers.extraction.date_candidates import (
    select_non_future_recall_date,
    select_recent_recall_date,
)
from agents.fetchers.extraction.detail_extractor import extract_detail_payload
from agents.fetchers.rendering.browser_fetch import fetch_browser_html
from agents.fetchers.rendering.static_fetch import StaticPage, fetch_static_page
from agents.fetchers.scraper_ingestion import SOURCE_REQUEST_HEADERS
from models.discovery_candidate import DiscoveryCandidate
from models.scraped_record import ScrapedRecallRecord
from models.search_candidate import canonicalize_url

StaticFetcher = Callable[..., Awaitable[StaticPage]]  # Injectable static page fetcher.
BrowserFetcher = Callable[..., Awaitable[tuple[str, str]]]  # Injectable browser HTML fetcher.

# Align with Brave freshness (past week) plus a small buffer for delayed indexing.
EARLY_WARNING_PUBLICATION_LOOKBACK_DAYS = 14

_HTML_CONTENT_TYPES = {  # MIME types treated as HTML for extraction.
    "",
    "text/html",
    "application/xhtml+xml",
    "application/xml",
    "text/xml",
}
_DYNAMIC_SHELL_MARKERS = (  # Substrings suggesting a JS-rendered shell page.
    "__next_data__",
    "enable javascript",
    "javascript is required",
    "id=\"app\"></div>",
    "id=\"root\"></div>",
)
_DETAIL_LINK_SIGNALS = (  # Path/label tokens that hint at recall detail pages.
    "recall",
    "alert",
    "warning",
    "withdrawal",
    "rappel",
    "alerte",
    "retrait",
    "rueckruf",
    "rückruf",
    "warnung",
)
_MAX_DISCOVERED_DETAIL_LINKS = 50  # Cap on listing-page detail link expansion.


class EarlyWarningIngestionError(ValueError):
    """Raised when a discovery URL cannot be ingested into a usable record."""

    pass


class UnsupportedContentError(EarlyWarningIngestionError):
    """Raised for MIME types that should be retained for a later adapter.

    Attributes:
        content_type: Unsupported MIME type from the response.
    """

    def __init__(self, content_type: str) -> None:
        """Initialize with the unsupported content type.

        Args:
            content_type: MIME type that could not be processed.
        """
        self.content_type = content_type
        super().__init__(f"unsupported content type: {content_type or 'unknown'}")


async def ingest_early_warning_url(
    url: str,
    *,
    client: httpx.AsyncClient,
    candidate: DiscoveryCandidate | None = None,
    minimum_text_characters: int = 240,
    timeout_seconds: float = 20.0,
    static_fetcher: StaticFetcher = fetch_static_page,
    browser_fetcher: BrowserFetcher = fetch_browser_html,
) -> ScrapedRecallRecord:
    """Fetch and normalize one arbitrary discovery URL.

    Static HTML is always attempted first. A browser is used only when the
    static response looks like a JavaScript shell or extracts too little text.

    Args:
        url: URL to fetch.
        client: Shared httpx client for static fetches.
        candidate: Optional search candidate for provenance metadata.
        minimum_text_characters: Minimum extracted visible text length.
        timeout_seconds: Browser fetch timeout in seconds.
        static_fetcher: Injectable static HTML fetcher.
        browser_fetcher: Injectable browser HTML fetcher.

    Returns:
        ScrapedRecallRecord with normalized payload and provenance.

    Raises:
        UnsupportedContentError: When the response MIME type is not HTML.
        EarlyWarningIngestionError: When extracted text is below the minimum.
    """
    canonical_requested = canonicalize_url(url)
    static_page = await static_fetcher(
        client,
        canonical_requested,
        headers=SOURCE_REQUEST_HEADERS,
    )
    if static_page.content_type not in _HTML_CONTENT_TYPES:
        raise UnsupportedContentError(static_page.content_type or "unknown")

    html = static_page.html
    final_url = canonicalize_url(static_page.final_url)
    payload = extract_detail_payload(
        source_url=final_url,
        html=html,
        date_languages=[candidate.language] if candidate else None,
    )
    fetch_method = "static"
    visible_text = str(payload.get("visible_text") or "").strip()

    if _needs_browser_fallback(html, visible_text, minimum_text_characters):
        browser_html, browser_final_url = await browser_fetcher(
            final_url,
            headers=SOURCE_REQUEST_HEADERS,
            timeout_ms=max(1, int(timeout_seconds * 1000)),
        )
        browser_payload = extract_detail_payload(
            source_url=canonicalize_url(browser_final_url),
            html=browser_html,
            date_languages=[candidate.language] if candidate else None,
        )
        browser_text = str(browser_payload.get("visible_text") or "").strip()
        if len(browser_text) > len(visible_text):
            html = browser_html
            payload = browser_payload
            visible_text = browser_text
            final_url = canonicalize_url(browser_final_url)
            fetch_method = "browser"

    if len(visible_text) < minimum_text_characters:
        raise EarlyWarningIngestionError(
            f"page text below minimum ({len(visible_text)} < {minimum_text_characters})"
        )

    title = _page_title(html, payload)
    detail_links = _discover_detail_links(html, final_url)
    content_hash = hashlib.sha256(visible_text.encode("utf-8")).hexdigest()
    publication_date = _preferred_publication_date(payload)
    aliases = list(dict.fromkeys([canonical_requested, final_url]))
    hostname = (urlsplit(final_url).hostname or "").lower()
    provenance: dict[str, Any] = {
        "discovery_method": "brave_search" if candidate else "arbitrary_url",
        "candidate_id": candidate.candidate_id if candidate else "",
        "query_ids": list(candidate.query_ids) if candidate else [],
        "search_title": candidate.title if candidate else "",
        "search_description": candidate.description if candidate else "",
        "filter_confidence": candidate.confidence if candidate else None,
        "filter_reasons": list(candidate.reasons) if candidate else [],
    }
    payload.update(
        {
            "source_url": final_url,
            "requested_url": canonical_requested,
            "final_url": final_url,
            "canonical_url": final_url,
            "redirected_url_aliases": aliases,
            "source_domain": hostname,
            "title": title,
            "detail_links": detail_links,
            "publication_date": publication_date,
            "content_hash": content_hash,
            "content_type": static_page.content_type or "text/html",
            "fetch_method": fetch_method,
            "provenance": provenance,
        }
    )
    return ScrapedRecallRecord(source_name=hostname or "early-warning", payload=payload)


async def ingest_url(
    url: str,
    *,
    client: httpx.AsyncClient,
    candidate: DiscoveryCandidate | None = None,
    minimum_text_characters: int = 240,
    timeout_seconds: float = 20.0,
) -> ScrapedRecallRecord:
    """Alias for ``ingest_early_warning_url`` with default fetchers.

    Args:
        url: URL to fetch.
        client: Shared httpx client.
        candidate: Optional search candidate for provenance.
        minimum_text_characters: Minimum extracted visible text length.
        timeout_seconds: Browser fetch timeout in seconds.

    Returns:
        ScrapedRecallRecord for the fetched page.
    """
    return await ingest_early_warning_url(
        url,
        client=client,
        candidate=candidate,
        minimum_text_characters=minimum_text_characters,
        timeout_seconds=timeout_seconds,
    )


def _needs_browser_fallback(html: str, visible_text: str, minimum: int) -> bool:
    """Return whether static extraction warrants a browser retry.

    Args:
        html: Raw HTML body.
        visible_text: Extracted visible text.
        minimum: Minimum acceptable text length.

    Returns:
        True when text is short or the page looks like a JS shell.
    """
    lowered = html.casefold()
    return len(visible_text) < minimum or any(marker in lowered for marker in _DYNAMIC_SHELL_MARKERS)


def _page_title(html: str, payload: dict[str, Any]) -> str:
    """Extract a page title from HTML or fall back to the source URL.

    Args:
        html: Page HTML.
        payload: Extracted detail payload (for source_url fallback).

    Returns:
        Best-effort page title string.
    """
    soup = BeautifulSoup(html, "html.parser")
    if soup.title and soup.title.string:
        title = " ".join(soup.title.string.split())
        if title:
            return title
    heading = soup.find("h1")
    if heading is not None:
        return heading.get_text(" ", strip=True)
    return str(payload.get("source_url") or "")


def _discover_detail_links(html: str, page_url: str) -> list[dict[str, str]]:
    """Collect likely recall-detail links for bounded listing-page expansion.

    Args:
        html: Listing/index page HTML.
        page_url: Canonical URL of the page (same-host filter).

    Returns:
        List of ``{"url", "title"}`` dicts up to the discovery cap.
    """
    soup = BeautifulSoup(html, "html.parser")
    page_host = (urlsplit(page_url).hostname or "").lower()
    discovered: dict[str, str] = {}
    for anchor in soup.find_all("a", href=True):
        label = " ".join(anchor.get_text(" ", strip=True).split())
        href = str(anchor.get("href") or "").strip()
        if not href:
            continue
        try:
            target = canonicalize_url(urljoin(page_url, href))
        except ValueError:
            continue
        parsed = urlsplit(target)
        target_host = (parsed.hostname or "").lower()
        if target == page_url or target_host != page_host:
            continue
        signal_text = f"{label} {parsed.path}".casefold()
        if not any(signal in signal_text for signal in _DETAIL_LINK_SIGNALS):
            continue
        discovered.setdefault(target, label or parsed.path.rsplit("/", 1)[-1])
        if len(discovered) >= _MAX_DISCOVERED_DETAIL_LINKS:
            break
    return [{"url": url, "title": title} for url, title in discovered.items()]


def _preferred_publication_date(payload: dict[str, Any]) -> str | None:
    """Select the best publication date from extracted date candidates.

    Prefers recent dates within the lookback window, then any non-future date.

    Args:
        payload: Detail payload containing published_date_candidates.

    Returns:
        ISO date string, or None when no usable candidate exists.
    """
    candidates = payload.get("published_date_candidates")
    sources = payload.get("published_date_candidate_sources")
    if not isinstance(candidates, list):
        return None
    source_map = sources if isinstance(sources, dict) else None
    values = [str(value) for value in candidates if str(value).strip()]
    if not values:
        return None
    # Prefer structured/selector candidates within the lookback window. If the
    # page was discovered late, retain its best non-future publication date so
    # the incident can display the actual date rather than "Not available".
    recent_date = select_recent_recall_date(
        values,
        lookback_days=EARLY_WARNING_PUBLICATION_LOOKBACK_DAYS,
        candidate_sources=source_map,
    )
    return recent_date or select_non_future_recall_date(
        values,
        candidate_sources=source_map,
    )
