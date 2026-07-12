from __future__ import annotations

import unittest

import httpx

from agents.fetchers.crawler.discovery import collapse_repeated_path_segments, normalize_resolved_url
from agents.fetchers.crawler.source_discovery import (
    LinkCandidate,
    looks_like_detail_url,
    looks_like_listing_url,
    score_recall_candidate,
    select_heuristic_seed_urls,
    _should_try_browser,
)


class UrlNormalizeTests(unittest.TestCase):
    def test_collapse_doubled_germany_path(self) -> None:
        path = "/DE/Home/DE/Home/home_node.html"
        self.assertEqual(collapse_repeated_path_segments(path), "/DE/Home/home_node.html")

    def test_normalize_resolved_url_keeps_query(self) -> None:
        url = "https://www.lebensmittelwarnung.de/DE/Home/DE/Home/home_node.html?x=1"
        self.assertEqual(
            normalize_resolved_url(url),
            "https://www.lebensmittelwarnung.de/DE/Home/home_node.html?x=1",
        )


class HeuristicSeedTests(unittest.TestCase):
    def test_detail_urls_are_penalized_vs_listings(self) -> None:
        listing = score_recall_candidate(
            "https://rappel.conso.gouv.fr/categorie/1",
            "Alimentation",
        )
        detail = score_recall_candidate(
            "https://rappel.conso.gouv.fr/fiche-rappel/22774/Interne",
            "Product",
        )
        self.assertGreater(listing, detail)
        self.assertTrue(looks_like_listing_url("https://alerts.food.gov.uk/news-alerts"))
        self.assertTrue(looks_like_detail_url("https://alerts.food.gov.uk/news-alerts/alert/FSA-AA-1"))

    def test_select_heuristic_seeds_prefers_listings_or_homepage(self) -> None:
        ranked = [
            LinkCandidate(
                url="https://rappel.conso.gouv.fr/fiche-rappel/1/Interne",
                anchor_text="detail",
                score=score_recall_candidate("https://rappel.conso.gouv.fr/fiche-rappel/1/Interne"),
            ),
            LinkCandidate(
                url="https://rappel.conso.gouv.fr/categorie/1",
                anchor_text="food recalls",
                score=score_recall_candidate("https://rappel.conso.gouv.fr/categorie/1", "food recalls"),
            ),
        ]
        ranked.sort(key=lambda item: (-item.score, item.url))
        seeds = select_heuristic_seed_urls(
            ranked,
            homepage_url="https://rappel.conso.gouv.fr/",
        )
        self.assertEqual(seeds, ["https://rappel.conso.gouv.fr/categorie/1"])

        detail_only = [
            LinkCandidate(
                url="https://rappel.conso.gouv.fr/fiche-rappel/1/Interne",
                anchor_text="detail",
                score=1,
            )
        ]
        seeds = select_heuristic_seed_urls(
            detail_only,
            homepage_url="https://rappel.conso.gouv.fr/",
        )
        self.assertEqual(seeds, ["https://rappel.conso.gouv.fr/"])


class BrowserFallbackPolicyTests(unittest.TestCase):
    def test_skips_browser_on_http_404(self) -> None:
        request = httpx.Request("GET", "https://example.com/missing")
        response = httpx.Response(404, request=request)
        exc = httpx.HTTPStatusError("not found", request=request, response=response)
        self.assertFalse(_should_try_browser(static_error=exc, html=""))

    def test_allows_browser_on_server_error(self) -> None:
        request = httpx.Request("GET", "https://example.com/x")
        response = httpx.Response(503, request=request)
        exc = httpx.HTTPStatusError("unavailable", request=request, response=response)
        self.assertTrue(_should_try_browser(static_error=exc, html=""))


if __name__ == "__main__":
    unittest.main()
