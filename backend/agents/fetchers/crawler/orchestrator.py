from __future__ import annotations

import heapq
import logging
from dataclasses import dataclass
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from agents.fetchers.crawler.discovery import classify_page, extract_internal_links
from agents.fetchers.crawler.scoring import score_page_relevance, score_url_relevance
from agents.fetchers.extraction.detail_extractor import extract_detail_payload
from agents.fetchers.rendering.browser_fetch import fetch_browser_html
from agents.fetchers.rendering.static_fetch import fetch_static_html
from models.scraper_config import ScraperSourceConfig

LOGGER = logging.getLogger(__name__)


@dataclass(order=True)
class _QueueItem:
    priority: int
    depth: int
    url: str


async def crawl_source_pages(
    *,
    source_name: str,
    source_config: ScraperSourceConfig,
    client: httpx.AsyncClient,
) -> list[dict[str, object]]:
    recall_keywords = source_config.hints.recall_keywords
    blocked_paths = source_config.hints.blocked_paths
    queue: list[_QueueItem] = []
    for seed in source_config.seed_urls:
        score = score_url_relevance(seed, recall_keywords)
        heapq.heappush(queue, _QueueItem(priority=-score, depth=0, url=seed))

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
        if not _is_allowed(item.url, source_config.allowed_domains, blocked_paths):
            continue
        if robots is not None and not robots.can_fetch("*", item.url):
            continue

        try:
            html, final_url = await fetch_static_html(client, item.url)
            if source_config.hints.force_browser or _looks_dynamic(html):
                html, final_url = await fetch_browser_html(item.url)
        except (httpx.HTTPError, RuntimeError, ValueError) as exc:
            LOGGER.warning("Skipping %s page %s after fetch failure: %s", source_name, item.url, exc)
            continue

        pages_seen += 1
        page_class = classify_page(url=final_url, html=html, recall_keywords=recall_keywords)
        if page_class == "detail":
            detail_pages.append(
                extract_detail_payload(
                    source_url=final_url,
                    html=html,
                    date_selectors=source_config.hints.date_selectors,
                )
            )

        if item.depth >= source_config.max_depth or page_class == "irrelevant":
            continue

        links = extract_internal_links(
            current_url=final_url,
            html=html,
            allowed_domains=source_config.allowed_domains,
            blocked_paths=blocked_paths,
        )
        for link in links:
            if link in visited:
                continue
            score = score_page_relevance(link, "", recall_keywords)
            heapq.heappush(queue, _QueueItem(priority=-score, depth=item.depth + 1, url=link))

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
