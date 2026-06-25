from __future__ import annotations

from urllib.parse import urldefrag, urljoin, urlparse

from bs4 import BeautifulSoup

PageClass = str

def classify_page(
    *,
    url: str,
    html: str,
    detail_page_keywords: list[str],
) -> PageClass:
    lowered_url = url.lower()
    if matches_detail_url(lowered_url, detail_page_keywords):
        return "detail"

    soup = BeautifulSoup(html, "html.parser")
    anchor_count = len(soup.find_all("a"))
    if anchor_count >= 8:
        return "listing"
    return "irrelevant"


def matches_detail_url(url: str, detail_page_keywords: list[str]) -> bool:
    lowered = url.lower()
    return any(keyword.lower() in lowered for keyword in detail_page_keywords)


def extract_internal_links(
    *,
    current_url: str,
    html: str,
    allowed_domains: list[str],
    blocked_paths: list[str],
) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    links: list[str] = []
    for anchor in soup.find_all("a"):
        href = anchor.get("href")
        if not href:
            continue
        absolute = urljoin(current_url, href)
        absolute, _fragment = urldefrag(absolute)
        parsed = urlparse(absolute)
        netloc = parsed.netloc.lower()
        path = parsed.path.lower()

        if parsed.scheme not in {"http", "https"}:
            continue
        if allowed_domains and not any(netloc.endswith(domain) for domain in allowed_domains):
            continue
        if any(path.startswith(blocked_path.lower()) for blocked_path in blocked_paths):
            continue
        links.append(absolute)

    return list(dict.fromkeys(links))
