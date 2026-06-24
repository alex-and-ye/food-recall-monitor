from __future__ import annotations

from bs4 import BeautifulSoup


def score_page_relevance(url: str, html: str, recall_keywords: list[str]) -> int:
    score = score_url_relevance(url, recall_keywords)
    if not html.strip():
        return score

    soup = BeautifulSoup(html, "html.parser")
    title = (soup.title.get_text(" ", strip=True) if soup.title else "").lower()
    text = soup.get_text(" ", strip=True).lower()[:4_000]

    for keyword in recall_keywords:
        lowered = keyword.lower()
        if lowered in title:
            score += 4
        if lowered in text:
            score += 1
    return score


def score_url_relevance(url: str, recall_keywords: list[str]) -> int:
    lowered = url.lower()
    score = 0
    for keyword in recall_keywords:
        if keyword.lower() in lowered:
            score += 3
    if any(token in lowered for token in ("recall", "alert", "withdraw", "allergen")):
        score += 2
    return score
