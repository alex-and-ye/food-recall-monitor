from __future__ import annotations

from urllib.parse import urldefrag, urljoin, urlparse

from bs4 import BeautifulSoup

PageClass = str

DETAIL_URL_TOKENS: tuple[str, ...] = (
    "/recall/",
    "/alert/",
    "/withdrawal/",
    "/notice/",
    "/fiche-rappel/",
)


def classify_page(
    *,
    url: str,
    html: str,
    recall_keywords: list[str],
) -> PageClass:
    lowered_url = url.lower()
    soup = BeautifulSoup(html, "html.parser")
    title = (soup.title.get_text(" ", strip=True) if soup.title else "").lower()
    text = soup.get_text(" ", strip=True).lower()
    anchor_count = len(soup.find_all("a"))

    keyword_hit = any(keyword.lower() in lowered_url or keyword.lower() in title for keyword in recall_keywords)
    text_keyword_hit = any(keyword.lower() in text for keyword in recall_keywords)

    if keyword_hit and text_keyword_hit:
        if any(token in lowered_url for token in DETAIL_URL_TOKENS):
            return "detail"
        if "risk" in text or "consumer" in text or "do not consume" in text:
            return "detail"

    if anchor_count >= 12 and any(token in lowered_url for token in ("search", "category", "recalls", "alerts")):
        return "listing"

    if text_keyword_hit and anchor_count >= 8:
        return "listing"

    return "irrelevant"


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
