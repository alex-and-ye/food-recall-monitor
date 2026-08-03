"""Automated discovery of scraper configuration from a source homepage.

Explores internal links with structural heuristics, uses LLM prompts to select
listing seeds and detail-page keywords, and assembles a ready-to-crawl
``SourceRegistryDocument`` with validated hints and fallbacks.
"""

import asyncio
import logging
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from agents.fetchers.crawler.discovery import extract_internal_links, matches_detail_url
from agents.fetchers.rendering.browser_fetch import fetch_browser_html
from agents.fetchers.rendering.static_fetch import fetch_static_html
from agents.llm import chat_json
from agents.prompts import DETAIL_PATTERN_DISCOVERY_SYSTEM_PROMPT, LISTING_DISCOVERY_SYSTEM_PROMPT
from config.agents import CLASSIFICATION_MODEL
from models.pipeline_progress import PipelineStage, ProgressReporter
from models.scraper_config import DEFAULT_LOOKBACK_DAYS, ScraperHints, ScraperSourceConfig
from models.source_registry import DiscoveryStatus, SourceRegistryDocument

# Module logger for discovery progress and LLM ranking steps.
LOGGER = logging.getLogger(__name__)

# Max ranked candidates included in discovery progress logs.
TOP_CANDIDATES_LOGGED = 8

# Language-agnostic path noise (assets / static), not recall vocabulary.
ASSET_PATH_MARKERS: tuple[str, ...] = (
    "/assets/",
    "/static/",
    "/files/",
    "/media/",
    "/css/",
    "/js/",
    "/image",
    "/icon",
    "/font",
    "/siteglobals/",
)

# Basenames treated as listing index pages rather than detail notices.
INDEX_BASENAMES: frozenset[str] = frozenset(
    {"index.html", "home.html", "home_node.html"}
)

# Upper bounds for breadth-first candidate exploration during discovery.
DISCOVERY_MAX_CANDIDATES = 40
# Max pages fetched while exploring listing/detail candidates.
DISCOVERY_MAX_PAGES = 25
# Max link-follow depth from seed URLs during discovery.
DISCOVERY_MAX_DEPTH = 2

# Max child links sampled from listing pages for detail-pattern LLM prompts.
CHILD_LINK_SAMPLE_SIZE = 40

# Minimum shared path-prefix count to treat a hub as listing-dense.
LISTING_DENSITY_MIN = 3

@dataclass(frozen=True)
class LinkCandidate:
    """Internal hyperlink with anchor text and a structural relevance score."""

    url: str
    anchor_text: str
    score: int

def derive_base_url_and_domains(homepage_url: str) -> tuple[str, list[str]]:
    """Derive canonical base URL and allowed domain variants from a homepage.

    Args:
        homepage_url: Absolute homepage URL for the recall source.

    Returns:
        Tuple of ``(base_url, allowed_domains)`` including www and non-www forms.

    Raises:
        ValueError: If ``homepage_url`` lacks a valid scheme or netloc.
    """
    parsed = urlparse(homepage_url.strip())
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid homepage URL: {homepage_url}")
    netloc = parsed.netloc.lower()
    base_url = f"{parsed.scheme}://{netloc}"
    domains = [netloc]
    if netloc.startswith("www."):
        domains.append(netloc.removeprefix("www."))
    else:
        domains.append(f"www.{netloc}")
    # Deduplicate while preserving order
    return base_url, list(dict.fromkeys(domains))

def score_recall_candidate(
    url: str,
    anchor_text: str = "",
    *,
    peer_urls: Sequence[str] | None = None,
) -> int:
    """Score a link for listing-oriented discovery using structure-only heuristics.

    Args:
        url: Candidate absolute URL.
        anchor_text: Anchor label (ignored; semantics handled by the LLM).
        peer_urls: Other URLs on the same page for listing-density boosts.

    Returns:
        Signed integer score; higher values favor listing hubs.
    """
    del anchor_text  # Semantics are handled by the LLM; scoring is shape-only.
    if _is_asset_url(url):
        return -20
    path = urlparse(url).path.lower()
    parts = _path_parts(url)
    score = 0
    if path in {"", "/"}:
        score -= 1
    if looks_like_detail_url(url):
        score -= 10
    elif looks_like_listing_url(url):
        score += 8
    elif len(parts) <= 2:
        score += 2
    if len(parts) >= 4:
        score -= 3
    score += _listing_hub_boost(url, peer_urls)
    return score

def score_detail_pattern_candidate(
    url: str,
    anchor_text: str = "",
    *,
    peer_urls: Sequence[str] | None = None,
) -> int:
    """Score a child link when sampling URLs for detail-keyword discovery.

    Args:
        url: Candidate absolute URL.
        anchor_text: Anchor label (ignored).
        peer_urls: Sibling URLs for cluster-density boosts.

    Returns:
        Signed integer score; higher values favor likely detail notices.
    """
    del anchor_text
    if _is_asset_url(url):
        return -20
    path = urlparse(url).path.lower()
    parts = _path_parts(url)
    score = 0
    if looks_like_detail_url(url) or looks_like_probable_detail_url(url):
        score += 20
    elif looks_like_listing_url(url):
        score -= 8
    if len(parts) >= 3:
        score += 3
    if _has_id_like_segment(parts):
        score += 4
    if re.search(r"\d{3,}", path):
        score += 2
    score += _detail_cluster_boost(url, peer_urls)
    return score

def looks_like_detail_url(url: str) -> bool:
    """Detect detail/notice URLs from path depth and id-like segments only.

    Args:
        url: Absolute URL to classify.

    Returns:
        True when structural signals match a single recall notice page.
    """
    if _is_asset_url(url):
        return False
    parts = _path_parts(url)
    if len(parts) < 2:
        return False
    basename = parts[-1]
    if _is_index_basename(basename):
        return False
    # Portal-style hosts prefix content with /___<host>/...
    if parts[0].startswith("___") and len(parts) >= 3:
        return True
    if len(parts) >= 3 and _has_id_like_segment(parts):
        return True
    if len(parts) >= 2 and _has_long_numeric_id(parts):
        return True
    if basename.endswith(".html") and len(parts) >= 3:
        return True
    if len(parts) >= 4:
        return True
    return False

def looks_like_probable_detail_url(url: str) -> bool:
    """Broader structural detail heuristic used for keyword clustering.

    Args:
        url: Absolute URL to classify.

    Returns:
        True for likely detail pages under looser path rules than
        ``looks_like_detail_url``.
    """
    if looks_like_detail_url(url):
        return True
    if looks_like_listing_url(url):
        return False
    if _is_asset_url(url):
        return False
    parts = _path_parts(url)
    if len(parts) < 2:
        return False
    if _is_index_basename(parts[-1]):
        return False
    if len(parts) >= 3:
        return True
    if _has_id_like_segment(parts):
        return True
    return False

def looks_like_listing_url(url: str) -> bool:
    """Detect listing or hub URLs from shallow index-shaped paths.

    Args:
        url: Absolute URL to classify.

    Returns:
        True when the path looks like an index or section root, not a notice.
    """
    if looks_like_detail_url(url):
        return False
    if _is_asset_url(url):
        return False
    parts = _path_parts(url)
    if not parts:
        return False
    basename = parts[-1]
    if _is_index_basename(basename):
        return True
    if basename.endswith("_node.html"):
        return True
    if len(parts) <= 2 and not _has_long_numeric_id(parts):
        return True
    return False

def max_listing_density(urls: Sequence[str]) -> int:
    """Return the highest shared path-prefix frequency among URLs.

    Args:
        urls: Collection of absolute URLs from a single page or hub.

    Returns:
        Maximum count of URLs sharing any one- or two-segment path prefix.
    """
    counts = _prefix_counts(urls)
    return max(counts.values()) if counts else 0

def select_heuristic_seed_urls(
    ranked: list[LinkCandidate],
    *,
    homepage_url: str,
    limit: int = 3,
) -> list[str]:
    """Choose listing seed URLs when LLM listing discovery fails or is empty.

    Args:
        ranked: Structure-scored link candidates from exploration.
        homepage_url: Fallback seed when no positive listing candidates exist.
        limit: Maximum number of seed URLs to return.

    Returns:
        Deduplicated listing URLs, or ``[homepage_url]`` as last resort.
    """
    listing_urls = [
        item.url
        for item in ranked
        if looks_like_listing_url(item.url) and item.score > 0
    ]
    if listing_urls:
        return list(dict.fromkeys(listing_urls))[:limit]
    # Prefer the homepage over detail-like candidates when LLM discovery failed.
    return [homepage_url]

def prefer_unfiltered_listing_urls(
    selected_urls: list[str],
    *,
    observed_urls: list[str],
) -> list[str]:
    """Prefer canonical listing URLs over filtered query-string variants.

    Args:
        selected_urls: Seed URLs chosen by discovery or LLM.
        observed_urls: URLs seen during exploration (lowercased for lookup).

    Returns:
        Seed list with query-stripped canonical listings substituted when
        an unfiltered form was observed and looks like a listing page.
    """
    observed = {url.lower() for url in observed_urls}
    preferred: list[str] = []
    for url in selected_urls:
        parsed = urlparse(url)
        canonical = parsed._replace(query="", fragment="").geturl()
        if parsed.query and canonical.lower() in observed and looks_like_listing_url(canonical):
            preferred.append(canonical)
        else:
            preferred.append(url)
    return list(dict.fromkeys(preferred))

def extract_link_candidates(
    *,
    current_url: str,
    html: str,
    allowed_domains: list[str],
    blocked_paths: list[str] | None = None,
) -> list[LinkCandidate]:
    """Parse anchor tags and score each internal link for discovery ranking.

    Args:
        current_url: Base URL for resolving relative hrefs.
        html: Page HTML to parse.
        allowed_domains: Permitted netloc suffixes.
        blocked_paths: Optional path prefixes to exclude.

    Returns:
        ``LinkCandidate`` list sorted by descending structural score.
    """
    soup = BeautifulSoup(html, "html.parser")
    blocked = blocked_paths or []
    raw: list[tuple[str, str]] = []
    seen: set[str] = set()

    for anchor in soup.find_all("a"):
        href = anchor.get("href")
        if not href:
            continue
        absolute_links = extract_internal_links(
            current_url=current_url,
            html=f'<a href="{href}"></a>',
            allowed_domains=allowed_domains,
            blocked_paths=blocked,
        )
        if not absolute_links:
            continue
        url = absolute_links[0]
        if url in seen:
            continue
        seen.add(url)
        anchor_text = " ".join(anchor.stripped_strings)[:160]
        raw.append((url, anchor_text))

    peer_urls = [url for url, _ in raw]
    candidates = [
        LinkCandidate(
            url=url,
            anchor_text=anchor_text,
            score=score_recall_candidate(url, anchor_text, peer_urls=peer_urls),
        )
        for url, anchor_text in raw
    ]
    candidates.sort(key=lambda item: (-item.score, item.url))
    return candidates

def rank_candidates(candidates: list[LinkCandidate], *, limit: int = DISCOVERY_MAX_CANDIDATES) -> list[LinkCandidate]:
    """Return the top-scoring link candidates up to a limit.

    Args:
        candidates: Pre-sorted or unsorted candidate list.
        limit: Maximum candidates to retain.

    Returns:
        First ``limit`` entries (caller should pre-sort for best results).
    """
    return candidates[:limit]

def rank_detail_pattern_candidates(
    candidates: list[LinkCandidate],
    *,
    limit: int = CHILD_LINK_SAMPLE_SIZE,
) -> list[LinkCandidate]:
    """Re-score candidates for detail-pattern discovery and return the top set.

    Args:
        candidates: Child links sampled from listing pages.
        limit: Maximum candidates to return.

    Returns:
        Candidates reordered by detail-pattern score, truncated to ``limit``.
    """
    peer_urls = [item.url for item in candidates]
    rescored = [
        LinkCandidate(
            url=item.url,
            anchor_text=item.anchor_text,
            score=score_detail_pattern_candidate(
                item.url,
                item.anchor_text,
                peer_urls=peer_urls,
            ),
        )
        for item in candidates
    ]
    rescored.sort(key=lambda item: (-item.score, item.url))
    return rescored[:limit]

async def discover_source_config(
    *,
    source_name: str,
    homepage_url: str,
    country_source: str | None = None,
    client: httpx.AsyncClient,
    reporter: ProgressReporter | None = None,
) -> SourceRegistryDocument:
    """Discover crawl configuration for a recall source from its homepage.

    Explores internal links, prompts an LLM for listing seeds and detail keywords,
    validates results against observed URLs, and builds a ready registry document.

    Args:
        source_name: Registry identifier for the source.
        homepage_url: Public homepage URL to start discovery.
        country_source: Display country label; defaults to ``source_name``.
        client: Async HTTP client for page fetches.
        reporter: Optional pipeline progress logger.

    Returns:
        ``SourceRegistryDocument`` with ``DiscoveryStatus.READY`` configuration.
    """
    base_url, allowed_domains = derive_base_url_and_domains(homepage_url)
    display_country = (country_source or source_name).strip() or source_name
    if reporter is not None:
        reporter.log(
            stage=PipelineStage.DISCOVERY,
            source=source_name,
            message="Starting source discovery",
            details={"homepage_url": homepage_url, "base_url": base_url},
        )

    homepage_html, homepage_final_url = await _fetch_html(client, homepage_url)
    candidates = extract_link_candidates(
        current_url=homepage_final_url,
        html=homepage_html,
        allowed_domains=allowed_domains,
    )
    # Explore structurally strong non-homepage pages for listing discovery.
    explored, explore_stats = await _explore_candidate_pages(
        client=client,
        seeds=[homepage_final_url, *[item.url for item in rank_candidates(candidates, limit=8)]],
        allowed_domains=allowed_domains,
    )
    merged_candidates = _merge_candidates(candidates, explored)
    ranked = rank_candidates(merged_candidates)
    if reporter is not None:
        reporter.log(
            stage=PipelineStage.DISCOVERY,
            source=source_name,
            message="Candidate exploration summary",
            details={
                "homepage_link_count": len(candidates),
                "pages_explored": explore_stats["pages_seen"],
                "fetch_failures": explore_stats["fetch_failures"],
                "unique_candidates": len(merged_candidates),
                "top_candidates": _candidate_summaries(ranked[:TOP_CANDIDATES_LOGGED]),
            },
        )

    listing_payload, listing_meta = await asyncio.to_thread(
        _request_listing_urls,
        homepage_url=homepage_final_url,
        candidates=ranked,
    )
    seed_urls = _filter_allowed_urls(listing_payload.get("seed_urls"), allowed_domains)
    used_listing_fallback = False
    if not seed_urls:
        used_listing_fallback = True
        seed_urls = select_heuristic_seed_urls(
            ranked,
            homepage_url=homepage_final_url,
        )
    else:
        # Drop accidental detail pages even when the model returns them.
        filtered_listings = [url for url in seed_urls if not looks_like_detail_url(url)]
        if filtered_listings:
            seed_urls = prefer_unfiltered_listing_urls(
                filtered_listings,
                observed_urls=[
                    homepage_final_url,
                    *[candidate.url for candidate in merged_candidates],
                ],
            )
        else:
            used_listing_fallback = True
            seed_urls = select_heuristic_seed_urls(
                ranked,
                homepage_url=homepage_final_url,
            )

    if reporter is not None:
        reporter.log(
            stage=PipelineStage.DISCOVERY,
            source=source_name,
            message="LLM listing selection result",
            details={
                "model": CLASSIFICATION_MODEL,
                "duration_seconds": listing_meta["duration_seconds"],
                "ok": listing_meta["ok"],
                "candidates_sent": listing_meta["candidates_sent"],
                "confidence": listing_payload.get("confidence"),
                "reason": listing_payload.get("reason"),
                "seed_urls": seed_urls,
                "used_heuristic_fallback": used_listing_fallback,
            },
        )

    child_samples: list[LinkCandidate] = []
    listing_fetch_failures = 0
    for listing_url in seed_urls[:3]:
        try:
            listing_html, listing_final = await _fetch_html(client, listing_url)
        except (httpx.HTTPError, RuntimeError, ValueError) as exc:
            listing_fetch_failures += 1
            LOGGER.warning("Discovery could not fetch listing %s: %s", listing_url, exc)
            continue
        child_samples.extend(
            extract_link_candidates(
                current_url=listing_final,
                html=listing_html,
                allowed_domains=allowed_domains,
            )
        )

    all_child_links = _merge_candidates([], child_samples)
    child_samples = rank_detail_pattern_candidates(
        all_child_links,
        limit=CHILD_LINK_SAMPLE_SIZE,
    )
    pattern_payload, pattern_meta = await asyncio.to_thread(
        _request_detail_patterns,
        seed_urls=seed_urls,
        child_links=child_samples,
    )
    detail_keywords = _normalize_path_fragments(pattern_payload.get("detail_page_keywords"))
    blocked_paths = _normalize_path_fragments(pattern_payload.get("blocked_paths"))
    date_languages = _normalize_languages(pattern_payload.get("date_languages"))
    blocked_paths = _filter_blocked_paths(blocked_paths, seed_urls=seed_urls)

    used_keyword_fallback = False
    validation_links = all_child_links + ranked
    detail_keywords = _filter_detail_keywords(
        detail_keywords,
        seed_urls=seed_urls,
        child_links=validation_links,
    )
    if not detail_keywords:
        used_keyword_fallback = True
        detail_keywords = (
            _infer_keywords_from_links(all_child_links)
            or _infer_keywords_from_links(ranked)
        )
        detail_keywords = _filter_detail_keywords(
            detail_keywords,
            seed_urls=seed_urls,
            child_links=validation_links,
        )

    if reporter is not None:
        reporter.log(
            stage=PipelineStage.DISCOVERY,
            source=source_name,
            message="LLM detail-pattern selection result",
            details={
                "model": CLASSIFICATION_MODEL,
                "duration_seconds": pattern_meta["duration_seconds"],
                "ok": pattern_meta["ok"],
                "child_links_sampled": len(child_samples),
                "listing_fetch_failures": listing_fetch_failures,
                "reason": pattern_payload.get("reason"),
                "detail_page_keywords": detail_keywords,
                "blocked_paths": blocked_paths,
                "date_languages": date_languages,
                "used_heuristic_fallback": used_keyword_fallback,
            },
        )

    config = ScraperSourceConfig(
        base_url=base_url,
        allowed_domains=allowed_domains,
        seed_urls=seed_urls,
        max_depth=1,
        max_pages_per_run=30,
        lookback_days=DEFAULT_LOOKBACK_DAYS,
        hints=ScraperHints(
            detail_page_keywords=detail_keywords,
            blocked_paths=blocked_paths,
            date_languages=date_languages,
            date_selectors=["time", ".date", "[datetime]", ".published-date"],
        ),
    )

    now = datetime.now(timezone.utc)
    document = SourceRegistryDocument(
        source_name=source_name,
        homepage_url=homepage_url,
        country_source=display_country,
        config=config,
        discovery_status=DiscoveryStatus.READY,
        discovery_reason=str(pattern_payload.get("reason") or listing_payload.get("reason") or "discovered"),
        discovered_at=now,
        updated_at=now,
    )
    if reporter is not None:
        reporter.log(
            stage=PipelineStage.DISCOVERY,
            source=source_name,
            message="Source discovery completed",
            details={
                "homepage_url": homepage_url,
                "seed_urls": config.seed_urls,
                "detail_page_keywords": config.hints.detail_page_keywords,
                "blocked_paths": config.hints.blocked_paths,
                "date_languages": config.hints.date_languages,
                "used_listing_fallback": used_listing_fallback,
                "used_keyword_fallback": used_keyword_fallback,
                "pages_explored": explore_stats["pages_seen"],
                "unique_candidates": len(merged_candidates),
            },
        )
    return document

def _path_parts(url: str) -> list[str]:
    """Return lowercase non-empty path segments for a URL."""
    return [part for part in urlparse(url).path.lower().split("/") if part]

def _is_index_basename(basename: str) -> bool:
    """Return whether a path basename denotes a listing index page."""
    return basename in INDEX_BASENAMES or basename.endswith("_node.html")

def _is_asset_url(url: str) -> bool:
    """Return whether the URL path matches static asset markers."""
    path = urlparse(url).path.lower()
    haystack = path if path.endswith("/") else f"{path}/"
    return any(marker in haystack or marker in path for marker in ASSET_PATH_MARKERS)

def _has_long_numeric_id(parts: Sequence[str]) -> bool:
    """Return whether any path segment contains four or more consecutive digits."""
    return any(re.search(r"\d{4,}", part) for part in parts)

def _has_id_like_segment(parts: Sequence[str]) -> bool:
    """Return whether any segment looks like a notice or document identifier."""
    for part in parts:
        stem = part.rsplit(".", maxsplit=1)[0]
        if re.search(r"\d{3,}", stem):
            return True
        # Alphanumeric notice ids such as FSA-AA-01-2024.
        if re.search(r"[a-z]{1,6}-\w*\d", stem, re.IGNORECASE):
            return True
    return False

def _prefix_counts(urls: Sequence[str]) -> dict[str, int]:
    """Count one- and two-segment path prefixes shared by multiple URLs."""
    counts: dict[str, int] = {}
    for url in urls:
        parts = _path_parts(url)
        for length in (1, 2):
            if len(parts) < length:
                continue
            prefix = "/" + "/".join(parts[:length]) + "/"
            if any(marker in prefix for marker in ASSET_PATH_MARKERS):
                continue
            counts[prefix] = counts.get(prefix, 0) + 1
    return counts

def _path_under_prefix(url: str, prefix: str) -> bool:
    """Return whether a URL path equals or nests under a normalized prefix."""
    path = urlparse(url).path.lower()
    normalized = path if path.endswith("/") else f"{path}/"
    return normalized.startswith(prefix) or prefix.rstrip("/") == path.rstrip("/")

def _listing_hub_boost(url: str, peer_urls: Sequence[str] | None) -> int:
    """Add score when many peer URLs share this URL's path prefix."""
    if not peer_urls:
        return 0
    parts = _path_parts(url)
    if not parts:
        return 0
    boost = 0
    for length in (1, 2):
        if len(parts) < length:
            continue
        prefix = "/" + "/".join(parts[:length]) + "/"
        # Count peers that live under this URL's path prefix (children / siblings).
        under = sum(
            1
            for peer in peer_urls
            if peer != url and _path_under_prefix(peer, prefix)
        )
        if under >= LISTING_DENSITY_MIN:
            boost += min(under, 12)
            break
    return boost

def _detail_cluster_boost(url: str, peer_urls: Sequence[str] | None) -> int:
    """Add score when probable detail URLs cluster under a shared two-segment prefix."""
    if not peer_urls or not looks_like_probable_detail_url(url):
        return 0
    parts = _path_parts(url)
    if len(parts) < 2:
        return 0
    prefix = "/" + "/".join(parts[:2]) + "/"
    siblings = sum(
        1
        for peer in peer_urls
        if peer != url and _path_under_prefix(peer, prefix)
    )
    if siblings >= 2:
        return min(siblings, 8)
    return 0

def _request_listing_urls(
    *,
    homepage_url: str,
    candidates: list[LinkCandidate],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Call the listing-discovery LLM and return payload plus timing metadata."""
    ranked_for_prompt = rank_candidates(candidates, limit=DISCOVERY_MAX_CANDIDATES)
    lines = [
        f"- url={item.url} | anchor={item.anchor_text!r} | score={item.score}"
        for item in ranked_for_prompt
    ]
    user_prompt = (
        f"Homepage URL: {homepage_url}\n\n"
        "Structure-ranked candidate links:\n"
        + ("\n".join(lines) if lines else "(no candidates)")
    )
    started = time.perf_counter()
    try:
        payload = chat_json(
            system_prompt=LISTING_DISCOVERY_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            model=CLASSIFICATION_MODEL,
        )
        return payload, {
            "ok": True,
            "duration_seconds": round(time.perf_counter() - started, 3),
            "candidates_sent": len(ranked_for_prompt),
        }
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Listing discovery LLM call failed: %s", exc)
        return (
            {"seed_urls": [], "confidence": 0.0, "reason": f"llm_error: {exc}"},
            {
                "ok": False,
                "duration_seconds": round(time.perf_counter() - started, 3),
                "candidates_sent": len(ranked_for_prompt),
            },
        )

def _request_detail_patterns(
    *,
    seed_urls: list[str],
    child_links: list[LinkCandidate],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Call the detail-pattern LLM and return payload plus timing metadata."""
    child_lines = [
        f"- url={item.url} | anchor={item.anchor_text!r} | score={item.score}"
        for item in child_links
    ]
    user_prompt = (
        "Listing URLs:\n"
        + "\n".join(f"- {url}" for url in seed_urls)
        + "\n\nSample child links:\n"
        + ("\n".join(child_lines) if child_lines else "(no child links)")
    )
    started = time.perf_counter()
    try:
        payload = chat_json(
            system_prompt=DETAIL_PATTERN_DISCOVERY_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            model=CLASSIFICATION_MODEL,
        )
        return payload, {
            "ok": True,
            "duration_seconds": round(time.perf_counter() - started, 3),
        }
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Detail pattern discovery LLM call failed: %s", exc)
        return (
            {
                "detail_page_keywords": [],
                "blocked_paths": [],
                "date_languages": [],
                "reason": f"llm_error: {exc}",
            },
            {
                "ok": False,
                "duration_seconds": round(time.perf_counter() - started, 3),
            },
        )

async def _fetch_html(client: httpx.AsyncClient, url: str) -> tuple[str, str]:
    """Fetch page HTML with static-first and optional browser fallback.

    Args:
        client: Async HTTP client for static fetch.
        url: Target page URL.

    Returns:
        Tuple of ``(html, final_url)`` after redirects.

    Raises:
        httpx.HTTPError: When static and browser fetches both fail.
        RuntimeError: When fetched content is empty.
    """
    html = ""
    final_url = url
    static_error: Exception | None = None
    try:
        html, final_url = await fetch_static_html(client, url)
    except httpx.HTTPError as exc:
        static_error = exc

    should_try_browser = _should_try_browser(static_error=static_error, html=html)
    if should_try_browser:
        try:
            html, final_url = await fetch_browser_html(url)
        except RuntimeError as browser_exc:
            if static_error is not None:
                raise static_error from browser_exc
            raise

    if not html.strip():
        if static_error is not None:
            raise static_error
        raise RuntimeError(f"Empty HTML content fetched for {url}")
    return html, final_url

def _should_try_browser(*, static_error: Exception | None, html: str) -> bool:
    """Decide whether discovery should retry a fetch with browser rendering."""
    if isinstance(static_error, httpx.HTTPStatusError):
        status = static_error.response.status_code
        # 4xx means the URL is wrong/unavailable; browser will not help and can crash
        # the Windows event loop via Playwright subprocess spawning.
        if 400 <= status < 500:
            return False
    if static_error is not None:
        return True
    return _looks_dynamic(html)

async def _explore_candidate_pages(
    *,
    client: httpx.AsyncClient,
    seeds: list[str],
    allowed_domains: list[str],
) -> tuple[list[LinkCandidate], dict[str, int]]:
    """Breadth-first explore seed pages to collect ranked link candidates.

    Args:
        client: Async HTTP client for page fetches.
        seeds: Starting URLs for exploration.
        allowed_domains: Permitted netloc suffixes.

    Returns:
        Tuple of collected candidates and stats ``pages_seen`` / ``fetch_failures``.
    """
    visited: set[str] = set()
    collected: list[LinkCandidate] = []
    queue = list(dict.fromkeys(seeds))
    pages_seen = 0
    fetch_failures = 0

    while queue and pages_seen < DISCOVERY_MAX_PAGES:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        try:
            html, final_url = await _fetch_html(client, url)
        except (httpx.HTTPError, RuntimeError, ValueError) as exc:
            fetch_failures += 1
            LOGGER.warning("Discovery explore skipped %s: %s", url, exc)
            continue
        pages_seen += 1
        page_candidates = extract_link_candidates(
            current_url=final_url,
            html=html,
            allowed_domains=allowed_domains,
        )
        collected.extend(page_candidates)

        child_urls = [item.url for item in page_candidates]
        density = max_listing_density(child_urls)
        if density >= LISTING_DENSITY_MIN:
            hub_score = (
                score_recall_candidate(final_url, peer_urls=child_urls)
                + min(density * 2, 24)
            )
            collected.append(
                LinkCandidate(
                    url=final_url,
                    anchor_text="(explored listing hub)",
                    score=hub_score,
                )
            )

        if pages_seen >= DISCOVERY_MAX_DEPTH:
            # Keep exploring only already-queued high-score links; do not deepen endlessly.
            continue
        for candidate in rank_candidates(page_candidates, limit=5):
            if candidate.url in visited:
                continue
            if _is_asset_url(candidate.url):
                continue
            if looks_like_detail_url(candidate.url):
                continue
            queue.append(candidate.url)

    return collected, {"pages_seen": pages_seen, "fetch_failures": fetch_failures}

def _candidate_summaries(candidates: list[LinkCandidate]) -> list[dict[str, object]]:
    """Build compact dict summaries for logging top discovery candidates."""
    return [
        {
            "url": item.url,
            "anchor_text": item.anchor_text[:80],
            "score": item.score,
        }
        for item in candidates
    ]

def _merge_candidates(*groups: list[LinkCandidate]) -> list[LinkCandidate]:
    """Merge candidate groups keeping the highest score per URL."""
    best: dict[str, LinkCandidate] = {}
    for group in groups:
        for item in group:
            existing = best.get(item.url)
            if existing is None or item.score > existing.score:
                best[item.url] = item
    merged = list(best.values())
    merged.sort(key=lambda item: (-item.score, item.url))
    return merged

def _filter_allowed_urls(value: object, allowed_domains: list[str]) -> list[str]:
    """Parse and filter a list of HTTP(S) URLs to allowed domains."""
    if not isinstance(value, list):
        return []
    filtered: list[str] = []
    for item in value:
        url = str(item).strip()
        if not url:
            continue
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            continue
        netloc = parsed.netloc.lower()
        if allowed_domains and not any(netloc.endswith(domain) for domain in allowed_domains):
            continue
        filtered.append(url)
    return list(dict.fromkeys(filtered))

def _normalize_path_fragments(value: object) -> list[str]:
    """Normalize LLM path fragments to lowercase absolute path prefixes."""
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    for item in value:
        text = str(item).strip().lower()
        if not text:
            continue
        if text.startswith("http://") or text.startswith("https://"):
            text = urlparse(text).path.lower()
        if not text.startswith("/"):
            text = f"/{text}"
        # Keep meaningful path fragments only.
        if len(text) < 2:
            continue
        normalized.append(text)
    return list(dict.fromkeys(normalized))

def _filter_detail_keywords(
    keywords: list[str],
    *,
    seed_urls: list[str],
    child_links: list[LinkCandidate],
) -> list[str]:
    """Keep keywords that match observed child links and do not match listing seeds.

    Args:
        keywords: Candidate detail-page path fragments.
        seed_urls: Listing seed URLs that keywords must not describe.
        child_links: Observed child links used to validate keyword matches.

    Returns:
        Filtered keyword list with seed collisions and non-matching entries removed.
    """
    seed_haystacks = [url.lower() for url in seed_urls]
    seed_paths = [urlparse(url).path.lower().rstrip("/") for url in seed_urls]
    seed_url_set = set(seed_haystacks)
    filtered: list[str] = []

    for keyword in keywords:
        keyword_lower = keyword.lower()
        keyword_key = keyword_lower.rstrip("/")
        if not keyword_key:
            continue
        if any(keyword_key in haystack for haystack in seed_haystacks):
            continue
        if any(
            keyword_key == path or path.endswith(keyword_key) or keyword_key in path
            for path in seed_paths
        ):
            continue

        matching_children = [
            item
            for item in child_links
            if keyword_lower in item.url.lower() and item.url.lower() not in seed_url_set
        ]
        if not matching_children:
            continue
        filtered.append(keyword)
    return filtered

def _filter_blocked_paths(blocked_paths: list[str], *, seed_urls: list[str]) -> list[str]:
    """Prevent discovered exclusions from blocking the listing pages themselves.

    Args:
        blocked_paths: Path prefixes to exclude during crawl.
        seed_urls: Listing seeds that must remain reachable.

    Returns:
        ``blocked_paths`` with entries that would block any seed removed.
    """
    seed_paths = [urlparse(url).path.lower() or "/" for url in seed_urls]
    return [
        blocked
        for blocked in blocked_paths
        if not any(seed_path.startswith(blocked.lower()) for seed_path in seed_paths)
    ]

def _normalize_languages(value: object) -> list[str]:
    """Parse and deduplicate two-letter ISO language codes from an LLM list."""
    if not isinstance(value, list):
        return []
    languages: list[str] = []
    for item in value:
        code = str(item).strip().lower().split("-", maxsplit=1)[0]
        if re.fullmatch(r"[a-z]{2}", code):
            languages.append(code)
    return list(dict.fromkeys(languages))

def _path_prefix_fragments(parts: list[str]) -> list[str]:
    """Emit generic path prefixes for clustering (no site-specific vocabulary).

    Args:
        parts: Lowercase URL path segments.

    Returns:
        Deduplicated ``/segment/`` style prefixes for keyword inference.
    """
    fragments: list[str] = []
    if not parts:
        return fragments
    if parts[0].startswith("___"):
        fragments.append(f"/{parts[0]}/")
        if len(parts) >= 2:
            fragments.append(f"/{parts[0]}/{parts[1]}/")
            fragments.append(f"/{parts[1]}/")
    if len(parts) >= 2:
        fragments.append("/" + "/".join(parts[:2]) + "/")
    fragments.append(f"/{parts[0]}/")
    return list(dict.fromkeys(fragments))

def _infer_keywords_from_links(links: list[LinkCandidate]) -> list[str]:
    """Infer detail-page keyword path prefixes from structurally detail-like URLs.

    Args:
        links: Candidate links observed during discovery.

    Returns:
        Up to five shared path-prefix keywords, preferring confirmed detail URLs.
    """
    confirmed_counts: dict[str, int] = {}
    probable_counts: dict[str, int] = {}

    for item in links:
        confirmed = looks_like_detail_url(item.url)
        probable = looks_like_probable_detail_url(item.url)
        if not (confirmed or probable):
            continue
        parts = _path_parts(item.url)
        if not parts:
            continue
        fragments = _path_prefix_fragments(parts)
        target = confirmed_counts if confirmed else probable_counts
        for fragment in fragments:
            if any(marker in fragment for marker in ASSET_PATH_MARKERS):
                continue
            target[fragment] = target.get(fragment, 0) + 1

    ranked_confirmed = _ranked_keyword_fragments(confirmed_counts, prefer_shared=True)
    if ranked_confirmed:
        ordered = list(ranked_confirmed)
        ordered.extend(
            fragment
            for fragment in _ranked_keyword_fragments(probable_counts, prefer_shared=True)
            if fragment not in ordered and probable_counts.get(fragment, 0) >= 2
        )
        return ordered[:5]

    return _ranked_keyword_fragments(probable_counts, prefer_shared=True)[:5]

def _ranked_keyword_fragments(
    counts: dict[str, int],
    *,
    prefer_shared: bool = True,
) -> list[str]:
    """Sort path fragments by frequency, optionally requiring multi-URL support."""
    ranked = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    if prefer_shared:
        multi = [fragment for fragment, count in ranked if count >= 2]
        if multi:
            return multi
    return [fragment for fragment, _count in ranked]

def _looks_dynamic(html: str) -> bool:
    """Return whether HTML appears JavaScript-heavy with little visible text."""
    script_tags = html.count("<script")
    text_like = len(" ".join(html.split()))
    return script_tags > 20 and text_like < 3_000

def smoke_match_detail_links(links: list[str], detail_page_keywords: list[str]) -> list[str]:
    """Filter links that match configured detail-page keywords (smoke-test helper).

    Args:
        links: Absolute URLs to test.
        detail_page_keywords: Path fragments indicating detail pages.

    Returns:
        Subset of ``links`` matching at least one keyword.
    """
    return [link for link in links if matches_detail_url(link, detail_page_keywords)]
