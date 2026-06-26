from __future__ import annotations

def score_page_relevance(url: str, html: str, detail_page_keywords: list[str]) -> int:
    del html
    return score_url_relevance(url, detail_page_keywords)


def score_url_relevance(url: str, detail_page_keywords: list[str]) -> int:
    lowered = url.lower()
    score = 0
    if any(keyword.lower() in lowered for keyword in detail_page_keywords):
        score += 12
    if any(token in lowered for token in ("faq", "support", "privacy", "contact", "mentions-legales")):
        score -= 4
    return score
