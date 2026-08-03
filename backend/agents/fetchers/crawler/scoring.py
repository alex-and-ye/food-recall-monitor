"""URL and page relevance scoring for crawl queue prioritization.

Assigns integer scores to candidate URLs so the orchestrator can prefer likely
recall detail pages and deprioritize low-value paths such as FAQ or legal pages.
"""

def score_page_relevance(url: str, html: str, detail_page_keywords: list[str]) -> int:
    """Score a fetched page for crawl priority (URL-only; HTML is ignored).

    Args:
        url: Absolute page URL.
        html: Page HTML (unused; scoring is URL-based for performance).
        detail_page_keywords: Path fragments that indicate recall detail pages.

    Returns:
        Integer relevance score; higher values are crawled sooner.
    """
    del html
    return score_url_relevance(url, detail_page_keywords)

def score_url_relevance(url: str, detail_page_keywords: list[str]) -> int:
    """Score a URL for crawl priority using keyword and noise heuristics.

    Args:
        url: Absolute URL to score.
        detail_page_keywords: Path fragments that boost detail-page likelihood.

    Returns:
        Integer score with bonuses for keyword matches and penalties for
        common non-recall path tokens.
    """
    lowered = url.lower()
    score = 0
    if any(keyword.lower() in lowered for keyword in detail_page_keywords):
        score += 12
    if any(token in lowered for token in ("faq", "support", "privacy", "contact", "mentions-legales")):
        score -= 4
    return score
