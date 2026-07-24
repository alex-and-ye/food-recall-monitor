from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

from agents.fetchers.extraction.date_candidates import select_recent_recall_date
from agents.fetchers.extraction.detail_extractor import extract_detail_payload
from agents.fetchers.rendering.browser_fetch import fetch_browser_html
from agents.fetchers.rendering.static_fetch import StaticPage, fetch_static_page
from agents.fetchers.scraper_ingestion import SOURCE_REQUEST_HEADERS
from models.discovery_candidate import DiscoveryCandidate
from models.scraped_record import ScrapedRecallRecord
from models.search_candidate import canonicalize_url

StaticFetcher = Callable[..., Awaitable[StaticPage]]
BrowserFetcher = Callable[..., Awaitable[tuple[str, str]]]

# Align with Brave freshness (past week) plus a small buffer for delayed indexing.
EARLY_WARNING_PUBLICATION_LOOKBACK_DAYS = 14

_HTML_CONTENT_TYPES = {
    "",
    "text/html",
    "application/xhtml+xml",
    "application/xml",
    "text/xml",
}
_DYNAMIC_SHELL_MARKERS = (
    "__next_data__",
    "enable javascript",
    "javascript is required",
    "id=\"app\"></div>",
    "id=\"root\"></div>",
)
_DETAIL_LINK_SIGNALS = (
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
_MAX_DISCOVERED_DETAIL_LINKS = 50


class EarlyWarningIngestionError(ValueError):
    pass


class UnsupportedContentError(EarlyWarningIngestionError):
    """Raised for MIME types that should be retained for a later adapter."""

    def __init__(self, content_type: str) -> None:
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
    return await ingest_early_warning_url(
        url,
        client=client,
        candidate=candidate,
        minimum_text_characters=minimum_text_characters,
        timeout_seconds=timeout_seconds,
    )


def _needs_browser_fallback(html: str, visible_text: str, minimum: int) -> bool:
    lowered = html.casefold()
    return len(visible_text) < minimum or any(marker in lowered for marker in _DYNAMIC_SHELL_MARKERS)


def _page_title(html: str, payload: dict[str, Any]) -> str:
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
    """Collect likely recall-detail links for bounded listing-page expansion."""
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
    candidates = payload.get("published_date_candidates")
    sources = payload.get("published_date_candidate_sources")
    if not isinstance(candidates, list):
        return None
    source_map = sources if isinstance(sources, dict) else None
    values = [str(value) for value in candidates if str(value).strip()]
    if not values:
        return None
    # Same selection policy as official recalls: reject future dates and
    # prefer structured/selector candidates within the lookback window.
    return select_recent_recall_date(
        values,
        lookback_days=EARLY_WARNING_PUBLICATION_LOOKBACK_DAYS,
        candidate_sources=source_map,
    )