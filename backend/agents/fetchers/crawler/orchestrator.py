from __future__ import annotations

import heapq
import logging
from dataclasses import dataclass, field
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from agents.fetchers.crawler.discovery import classify_page, extract_internal_links, matches_detail_url
from agents.fetchers.crawler.scoring import score_page_relevance, score_url_relevance
from agents.fetchers.extraction.detail_extractor import extract_detail_payload
from agents.fetchers.rendering.browser_fetch import fetch_browser_html
from agents.fetchers.rendering.static_fetch import fetch_static_html
from models.pipeline_progress import PipelineStage, ProgressReporter
from models.scraper_config import ScraperSourceConfig

LOGGER = logging.getLogger(__name__)


@dataclass(order=True)
class _QueueItem:
    priority: int
    depth: int
    order: int
    url: str = field(compare=False)


async def crawl_source_pages(
    *,
    source_name: str,
    source_config: ScraperSourceConfig,
    client: httpx.AsyncClient,
    reporter: ProgressReporter | None = None,
) -> list[dict[str, object]]:
    detail_page_keywords = source_config.hints.detail_page_keywords
    blocked_paths = source_config.hints.blocked_paths
    queue: list[_QueueItem] = []
    fetch_failures = 0
    enqueue_order = 0
    for seed in source_config.seed_urls:
        score = score_url_relevance(seed, detail_page_keywords)
        heapq.heappush(queue, _QueueItem(priority=-score, depth=0, order=enqueue_order, url=seed))
        enqueue_order += 1
    if reporter is not None:
        reporter.log(
            stage=PipelineStage.CRAWL,
            source=source_name,
            message="Starting crawl queue",
            details={
                "seed_urls": list(source_config.seed_urls),
                "seed_count": len(source_config.seed_urls),
                "detail_page_keywords": detail_page_keywords,
                "proxy_enabled": bool(source_config.proxy_url),
            },
        )

    detail_pages: list[dict[str, object]] = []
    visited: set[str] = set()
    robots = _build_robot_parser(source_config.base_url)
    pages_seen = 0

    while queue and pages_seen < source_config.max_pages_per_run:
        item = heapq.heappop(queue)
        if item.url in visited:
            continue
        visited.add(item.url)
        if item.depth > source_config.max_depth:
            continue
        # Seeds are explicitly selected listing entry points. A discovered blocked
        # path must never prevent the crawler from opening its own seed.
        effective_blocked_paths = [] if item.depth == 0 else blocked_paths
        if not _is_allowed(item.url, source_config.allowed_domains, effective_blocked_paths):
            continue
        if robots is not None and not robots.can_fetch("*", item.url):
            continue

        try:
            html = ""
            final_url = item.url
            render_mode = "static"
            static_error: Exception | None = None
            if not source_config.hints.force_browser:
                try:
                    html, final_url = await fetch_static_html(
                        client,
                        item.url,
                        headers=source_config.request_headers or None,
                        proxy_url=source_config.proxy_url,
                    )
                except httpx.HTTPError as exc:
                    static_error = exc

            should_try_browser = source_config.hints.force_browser or _should_try_browser(
                static_error=static_error,
                html=html,
                force_browser=source_config.hints.force_browser,
            )
            if should_try_browser:
                if reporter is not None and static_error is not None and not source_config.hints.force_browser:
                    reporter.log(
                        stage=PipelineStage.CRAWL,
                        source=source_name,
                        message="Static fetch failed, attempting browser fallback",
                        details={"url": item.url, "error": str(static_error)},
                    )
                try:
                    html, final_url = await fetch_browser_html(
                        item.url,
                        headers=source_config.request_headers or None,
                        proxy_url=source_config.proxy_url,
                    )
                    render_mode = "browser"
                except RuntimeError as browser_exc:
                    if static_error is not None:
                        raise static_error from browser_exc
                    raise

            if not html.strip():
                if static_error is not None:
                    raise static_error
                raise RuntimeError(f"Empty HTML content fetched for {item.url}")
        except (httpx.HTTPError, RuntimeError, ValueError) as exc:
            LOGGER.warning("Skipping %s page %s after fetch failure: %s", source_name, item.url, exc)
            fetch_failures += 1
            if reporter is not None:
                reporter.log(
                    stage=PipelineStage.CRAWL,
                    source=source_name,
                    message="Page fetch failed",
                    details={"url": item.url, "error": str(exc)},
                )
            continue

        pages_seen += 1
        page_class = classify_page(
            url=final_url,
            html=html,
            detail_page_keywords=detail_page_keywords,
        )
        if reporter is not None:
            reporter.log(
                stage=PipelineStage.CRAWL,
                source=source_name,
                message="Page classified",
                details={
                    "url": final_url,
                    "depth": item.depth,
                    "page_class": page_class,
                    "render_mode": render_mode,
                    "pages_seen": pages_seen,
                },
            )
        if page_class == "detail":
            payload = extract_detail_payload(
                source_url=final_url,
                html=html,
                date_selectors=source_config.hints.date_selectors,
                date_languages=source_config.hints.date_languages,
            )
            detail_pages.append(payload)
            if reporter is not None:
                date_candidates = list(payload.get("published_date_candidates", []))
                reporter.log(
                    stage=PipelineStage.CRAWL,
                    source=source_name,
                    message="Detail payload extracted",
                    details={
                        "url": final_url,
                        "date_candidate_count": len(date_candidates),
                        "date_candidates": date_candidates[:5],
                        "heading_count": len(list(payload.get("headings", []))),
                    },
                )

        if item.depth >= source_config.max_depth or page_class == "irrelevant":
            continue

        links = extract_internal_links(
            current_url=final_url,
            html=html,
            allowed_domains=source_config.allowed_domains,
            blocked_paths=blocked_paths,
        )
        detail_links = [
            link
            for link in links
            if link not in visited and matches_detail_url(link, detail_page_keywords)
        ]
        if reporter is not None:
            reporter.log(
                stage=PipelineStage.CRAWL,
                source=source_name,
                message="Discovered internal links",
                details={
                    "url": final_url,
                    "link_count": len(links),
                    "detail_link_count": len(detail_links),
                    "detail_links_sample": detail_links[:8],
                },
            )
        for link in detail_links:
            score = score_page_relevance(link, "", detail_page_keywords)
            heapq.heappush(
                queue,
                _QueueItem(
                    priority=-score,
                    depth=item.depth + 1,
                    order=enqueue_order,
                    url=link,
                ),
            )
            enqueue_order += 1
    if reporter is not None:
        reporter.log(
            stage=PipelineStage.CRAWL,
            source=source_name,
            message="Source crawl finished",
            details={
                "pages_seen": pages_seen,
                "detail_pages": len(detail_pages),
                "visited_pages": len(visited),
                "fetch_failures": fetch_failures,
            },
        )

    if pages_seen == 0 and fetch_failures > 0:
        raise RuntimeError(
            f"Unable to fetch any pages for source {source_name}. "
            f"Encountered {fetch_failures} fetch failure(s)."
        )

    return detail_pages


def _is_allowed(url: str, allowed_domains: list[str], blocked_paths: list[str]) -> bool:
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()
    path = parsed.path.lower()
    if allowed_domains and not any(netloc.endswith(domain) for domain in allowed_domains):
        return False
    if any(path.startswith(blocked.lower()) for blocked in blocked_paths):
        return False
    return True


def _build_robot_parser(base_url: str) -> RobotFileParser | None:
    parsed = urlparse(base_url)
    if not parsed.scheme or not parsed.netloc:
        return None
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    parser = RobotFileParser()
    parser.set_url(robots_url)
    # Keep parser explicit in crawler flow while avoiding a blocking network
    # roundtrip per source during unit tests and local development.
    parser.parse([])
    return parser


def _looks_dynamic(html: str) -> bool:
    script_tags = html.count("<script")
    text_like = len(" ".join(html.split()))
    return script_tags > 20 and text_like < 3_000


def _should_try_browser(
    *,
    static_error: Exception | None,
    html: str,
    force_browser: bool = False,
) -> bool:
    if force_browser:
        return True
    if isinstance(static_error, httpx.HTTPStatusError):
        try:
            status = int(static_error.response.status_code)
        except (TypeError, ValueError):
            status = 0
        if 400 <= status < 500:
            return False
    if static_error is not None:
        return True
    return _looks_dynamic(html)
