"""HTML page classification and internal link extraction for crawlers.

Classifies fetched pages as listing, detail, or irrelevant and extracts
same-domain links suitable for breadth-first recall crawling.
"""

import re
from urllib.parse import urldefrag, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

PageClass = str

def classify_page(
    *,
    url: str,
    html: str,
    detail_page_keywords: list[str],
) -> PageClass:
    """Classify a fetched page as a listing, detail, or irrelevant page.

    Uses URL keyword matches and anchor density to distinguish index pages
    from individual recall notices.

    Args:
        url: Final URL of the fetched page.
        html: Raw HTML content.
        detail_page_keywords: Path fragments associated with detail pages.

    Returns:
        ``"listing"``, ``"detail"``, or ``"irrelevant"``.
    """
    lowered_url = url.lower()
    keyword_match = matches_detail_url(lowered_url, detail_page_keywords)
    soup = BeautifulSoup(html, "html.parser")
    anchor_count = len(soup.find_all("a"))

    if keyword_match:
        # Overly broad keywords can match listing index URLs. Prefer listing when the
        # page is link-heavy and the path itself does not look like a single notice.
        if anchor_count >= 8 and _path_looks_like_index(lowered_url):
            return "listing"
        return "detail"

    if anchor_count >= 8:
        return "listing"
    return "irrelevant"

def matches_detail_url(url: str, detail_page_keywords: list[str]) -> bool:
    """Return whether any detail keyword appears in the URL path.

    Args:
        url: URL to test (case-insensitive matching).
        detail_page_keywords: Substrings that indicate a detail page.

    Returns:
        True if at least one keyword is contained in ``url``.
    """
    lowered = url.lower()
    return any(keyword.lower() in lowered for keyword in detail_page_keywords)

def _path_looks_like_index(url: str) -> bool:
    """Return whether the URL path resembles a listing or section index."""
    path = urlparse(url).path.lower().rstrip("/")
    if not path or path.endswith("_node") or path.endswith("_node.html"):
        return True
    basename = path.rsplit("/", maxsplit=1)[-1]
    index_names = {
        "",
        "index",
        "index.html",
        "home",
        "home.html",
        "list",
        "listing",
        "search",
        "results",
    }
    if basename in index_names:
        return True
    # Shallow section roots without a long id tend to be listings.
    parts = [part for part in path.split("/") if part]
    if len(parts) <= 3 and not any(re.search(r"\d{4,}", part) for part in parts):
        if any(token in path for token in ("recall", "alert", "rappel", "warnung", "meldung", "home")):
            return True
    return False

def collapse_repeated_path_segments(path: str) -> str:
    """Collapse duplicated path prefixes in a URL path.

    Example: ``/DE/Home/DE/Home/foo`` becomes ``/DE/Home/foo``.

    Args:
        path: URL path component (with or without leading slash).

    Returns:
        Path with consecutive duplicate segment blocks removed.
    """
    if not path or path == "/":
        return path or "/"
    trailing_slash = path.endswith("/")
    parts = [part for part in path.split("/") if part]
    changed = True
    while changed:
        changed = False
        max_block = min(4, len(parts) // 2)
        for block_size in range(max_block, 0, -1):
            for index in range(0, len(parts) - 2 * block_size + 1):
                left = parts[index : index + block_size]
                right = parts[index + block_size : index + 2 * block_size]
                if left == right:
                    parts = parts[: index + block_size] + parts[index + 2 * block_size :]
                    changed = True
                    break
            if changed:
                break
    rebuilt = "/" + "/".join(parts)
    if trailing_slash and rebuilt != "/":
        rebuilt += "/"
    return rebuilt or "/"

def normalize_resolved_url(url: str) -> str:
    """Normalize a resolved absolute URL by deduplicating path segments.

    Args:
        url: Absolute URL after resolution or redirect.

    Returns:
        URL with collapsed repeated path segments.
    """
    parsed = urlparse(url)
    normalized_path = collapse_repeated_path_segments(parsed.path)
    return urlunparse(parsed._replace(path=normalized_path))

def extract_internal_links(
    *,
    current_url: str,
    html: str,
    allowed_domains: list[str],
    blocked_paths: list[str],
) -> list[str]:
    """Extract deduplicated internal HTTP(S) links from page HTML.

    Args:
        current_url: Base URL for resolving relative ``href`` values.
        html: Page HTML to parse.
        allowed_domains: Netloc suffixes permitted; empty list allows all domains.
        blocked_paths: Path prefixes to exclude (case-insensitive).

    Returns:
        Ordered list of unique absolute URLs passing domain and path filters.
    """
    soup = BeautifulSoup(html, "html.parser")
    links: list[str] = []
    for anchor in soup.find_all("a"):
        href = anchor.get("href")
        if not href:
            continue
        absolute = normalize_resolved_url(urljoin(current_url, href))
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
