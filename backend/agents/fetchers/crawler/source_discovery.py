from __future__ import annotations

import logging
import re
import time
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
from models.pipeline_progress import ProgressReporter
from models.scraper_config import DEFAULT_LOOKBACK_DAYS, ScraperHints, ScraperSourceConfig
from models.source_registry import SourceRegistryDocument

LOGGER = logging.getLogger(__name__)

TOP_CANDIDATES_LOGGED = 8

RECALL_TOKENS: tuple[str, ...] = (
    "recall",
    "alert",
    "rappel",
    "warnung",
    "rückruf",
    "ruckruf",
    "withdrawal",
    "rücknahme",
    "rucknahme",
    "food-alert",
    "news-alerts",
    "lebensmittel",
    "fiche-rappel",
    "product-recall",
    "safety-alert",
    "categorie",
    "home_node",
)

NEGATIVE_TOKENS: tuple[str, ...] = (
    "faq",
    "support",
    "privacy",
    "contact",
    "cookie",
    "mentions-legales",
    "about",
    "login",
    "career",
    "presse",
    "press",
    "barrierefreiheit",
    "datenschutz",
    "feedback",
    "subscribe",
)

LISTING_PATH_TOKENS: tuple[str, ...] = (
    "/categorie/",
    "/news-alerts",
    "home_node",
    "/recalls",
    "/rappel",
    "/warnung",
)

DETAIL_PATH_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"/fiche-rappel/\d+", re.IGNORECASE),
    re.compile(r"/news-alerts/alert/", re.IGNORECASE),
    re.compile(r"/alert/fsa-[a-z0-9-]+", re.IGNORECASE),
    # Portal-style detail hosts often prefix content with /___<host>/...
    re.compile(r"/___[^/]+/", re.IGNORECASE),
    re.compile(r"/meldungen/", re.IGNORECASE),
)

DISCOVERY_MAX_CANDIDATES = 25
DISCOVERY_MAX_PAGES = 25
DISCOVERY_MAX_DEPTH = 2
CHILD_LINK_SAMPLE_SIZE = 40


@dataclass(frozen=True)
class LinkCandidate:
    url: str
    anchor_text: str
    score: int


def derive_base_url_and_domains(homepage_url: str) -> tuple[str, list[str]]:
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


def score_recall_candidate(url: str, anchor_text: str = "") -> int:
    haystack = f"{url} {anchor_text}".lower()
    path = urlparse(url).path.lower()
    score = 0
    for token in RECALL_TOKENS:
        if token in haystack:
            score += 4
    for token in NEGATIVE_TOKENS:
        if token in haystack:
            score -= 5
    if path in {"", "/"}:
        score -= 1
    if looks_like_detail_url(url):
        score -= 10
    elif looks_like_listing_url(url):
        score += 8
    return score


def score_detail_pattern_candidate(url: str, anchor_text: str = "") -> int:
    """Prefer likely detail/notice links when sampling children for keyword discovery."""
    haystack = f"{url} {anchor_text}".lower()
    path = urlparse(url).path.lower()
    score = 0
    for token in RECALL_TOKENS:
        if token in haystack:
            score += 4
    for token in NEGATIVE_TOKENS:
        if token in haystack:
            score -= 5
    if looks_like_detail_url(url) or looks_like_probable_detail_url(url):
        score += 20
    elif looks_like_listing_url(url):
        score -= 8
    parts = [part for part in path.split("/") if part]
    if len(parts) >= 3:
        score += 3
    if re.search(r"\d{3,}", path):
        score += 4
    return score


def looks_like_detail_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(pattern.search(path) for pattern in DETAIL_PATH_PATTERNS)


def looks_like_probable_detail_url(url: str) -> bool:
    """Heuristic detail detection beyond known path patterns (source-agnostic)."""
    if looks_like_detail_url(url):
        return True
    if looks_like_listing_url(url):
        return False
    path = urlparse(url).path.lower().rstrip("/")
    parts = [part for part in path.split("/") if part]
    if len(parts) < 2:
        return False
    basename = parts[-1]
    if basename.endswith("_node.html") or basename in {"index.html", "home.html", "home_node.html"}:
        return False
    if re.search(r"\d{4,}", path):
        return True
    if basename.endswith(".html") and len(parts) >= 3:
        return True
    detailish_tokens = ("alert", "rappel", "meldung", "warnung", "recall", "notice", "withdrawal")
    if len(parts) >= 3 and any(token in part for part in parts for token in detailish_tokens):
        return True
    if len(parts) >= 4:
        return True
    return False


def looks_like_listing_url(url: str) -> bool:
    if looks_like_detail_url(url):
        return False
    path = urlparse(url).path.lower().rstrip("/")
    haystack = path + "/"
    if any(token in haystack for token in LISTING_PATH_TOKENS):
        # Tokens like "/recalls" also appear inside detail paths; only treat shallow
        # roots (or known index pages) as listings.
        parts = [part for part in path.split("/") if part]
        if len(parts) <= 2:
            return True
        basename = parts[-1] if parts else ""
        if basename.endswith("_node.html") or basename in {"index.html", "home.html"}:
            return True
        return False
    # Shallow recall-ish index pages without a long numeric id.
    if re.search(r"/(recalls?|alerts?|rappels?)(/|$)", path) and not re.search(r"/\d{4,}(/|$)", path):
        parts = [part for part in path.split("/") if part]
        return len(parts) <= 2
    return False


def select_heuristic_seed_urls(
    ranked: list[LinkCandidate],
    *,
    homepage_url: str,
    limit: int = 3,
) -> list[str]:
    listing_urls = [item.url for item in ranked if looks_like_listing_url(item.url) and item.score > 0]
    if listing_urls:
        return list(dict.fromkeys(listing_urls))[:limit]
    # Prefer the homepage over detail-like candidates when LLM discovery failed.
    return [homepage_url]


def prefer_unfiltered_listing_urls(
    selected_urls: list[str],
    *,
    observed_urls: list[str],
) -> list[str]:
    """Prefer an observed canonical listing over a filtered query variant."""
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
    soup = BeautifulSoup(html, "html.parser")
    blocked = blocked_paths or []
    candidates: list[LinkCandidate] = []
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
        candidates.append(
            LinkCandidate(
                url=url,
                anchor_text=anchor_text,
                score=score_recall_candidate(url, anchor_text),
            )
        )

    candidates.sort(key=lambda item: (-item.score, item.url))
    return candidates


def rank_candidates(candidates: list[LinkCandidate], *, limit: int = DISCOVERY_MAX_CANDIDATES) -> list[LinkCandidate]:
    return candidates[:limit]


def rank_detail_pattern_candidates(
    candidates: list[LinkCandidate],
    *,
    limit: int = CHILD_LINK_SAMPLE_SIZE,
) -> list[LinkCandidate]:
    rescored = [
        LinkCandidate(
            url=item.url,
            anchor_text=item.anchor_text,
            score=score_detail_pattern_candidate(item.url, item.anchor_text),
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
    base_url, allowed_domains = derive_base_url_and_domains(homepage_url)
    display_country = (country_source or source_name).strip() or source_name
    if reporter is not None:
        reporter.log(
            stage="discovery",
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
    # Also explore a few high-scoring non-homepage pages for listing discovery.
    explored, explore_stats = await _explore_candidate_pages(
        client=client,
        seeds=[homepage_final_url, *[item.url for item in rank_candidates(candidates, limit=8)]],
        allowed_domains=allowed_domains,
    )
    merged_candidates = _merge_candidates(candidates, explored)
    ranked = rank_candidates(merged_candidates)
    if reporter is not None:
        reporter.log(
            stage="discovery",
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

    listing_payload, listing_meta = _request_listing_urls(
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
            stage="discovery",
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
    pattern_payload, pattern_meta = _request_detail_patterns(
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
            stage="discovery",
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
        discovery_status="ready",
        discovery_reason=str(pattern_payload.get("reason") or listing_payload.get("reason") or "discovered"),
        discovered_at=now,
        updated_at=now,
    )
    if reporter is not None:
        reporter.log(
            stage="discovery",
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


def _request_listing_urls(
    *,
    homepage_url: str,
    candidates: list[LinkCandidate],
) -> tuple[dict[str, Any], dict[str, Any]]:
    ranked_for_prompt = rank_candidates(candidates, limit=DISCOVERY_MAX_CANDIDATES)
    lines = [
        f"- url={item.url} | anchor={item.anchor_text!r} | score={item.score}"
        for item in ranked_for_prompt
    ]
    user_prompt = (
        f"Homepage URL: {homepage_url}\n\n"
        "Ranked candidate links:\n"
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
        if pages_seen >= DISCOVERY_MAX_DEPTH:
            # Keep exploring only already-queued high-score links; do not deepen endlessly.
            continue
        for candidate in rank_candidates(page_candidates, limit=5):
            if candidate.url in visited:
                continue
            if looks_like_detail_url(candidate.url):
                continue
            if candidate.score > 0:
                queue.append(candidate.url)

    return collected, {"pages_seen": pages_seen, "fetch_failures": fetch_failures}


def _candidate_summaries(candidates: list[LinkCandidate]) -> list[dict[str, object]]:
    return [
        {
            "url": item.url,
            "anchor_text": item.anchor_text[:80],
            "score": item.score,
        }
        for item in candidates
    ]


def _merge_candidates(*groups: list[LinkCandidate]) -> list[LinkCandidate]:
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
    """Keep keywords that match observed child links and do not match listing seeds."""
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
    """Prevent discovered exclusions from blocking the listing pages themselves."""
    seed_paths = [urlparse(url).path.lower() or "/" for url in seed_urls]
    return [
        blocked
        for blocked in blocked_paths
        if not any(seed_path.startswith(blocked.lower()) for seed_path in seed_paths)
    ]


def _normalize_languages(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    languages: list[str] = []
    for item in value:
        code = str(item).strip().lower().split("-", maxsplit=1)[0]
        if re.fullmatch(r"[a-z]{2}", code):
            languages.append(code)
    return list(dict.fromkeys(languages))


def _infer_keywords_from_links(links: list[LinkCandidate]) -> list[str]:
    """Heuristic fallback: path prefixes shared by detail-like URLs."""
    skip_markers = (
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
    confirmed_counts: dict[str, int] = {}
    probable_counts: dict[str, int] = {}

    for item in links:
        confirmed = looks_like_detail_url(item.url)
        probable = looks_like_probable_detail_url(item.url)
        if not (confirmed or probable):
            continue
        path = urlparse(item.url).path.lower().rstrip("/")
        parts = [part for part in path.split("/") if part]
        if not parts:
            continue
        fragments: list[str] = []
        if parts[0] == "fiche-rappel":
            fragments.append("/fiche-rappel/")
        elif len(parts) >= 2 and parts[0] == "news-alerts" and parts[1] == "alert":
            fragments.append("/news-alerts/alert/")
        elif parts[0].startswith("___"):
            fragments.append(f"/{parts[0]}/")
            if len(parts) >= 2:
                fragments.append(f"/{parts[0]}/{parts[1]}/")
                fragments.append(f"/{parts[1]}/")
        elif len(parts) >= 2:
            fragments.append("/" + "/".join(parts[:2]) + "/")
        else:
            fragments.append(f"/{parts[0]}/")

        target = confirmed_counts if confirmed else probable_counts
        for fragment in fragments:
            if any(marker in fragment for marker in skip_markers):
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
    ranked = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    if prefer_shared:
        multi = [fragment for fragment, count in ranked if count >= 2]
        if multi:
            return multi
    return [fragment for fragment, _count in ranked]


def _looks_dynamic(html: str) -> bool:
    script_tags = html.count("<script")
    text_like = len(" ".join(html.split()))
    return script_tags > 20 and text_like < 3_000


def smoke_match_detail_links(links: list[str], detail_page_keywords: list[str]) -> list[str]:
    return [link for link in links if matches_detail_url(link, detail_page_keywords)]
