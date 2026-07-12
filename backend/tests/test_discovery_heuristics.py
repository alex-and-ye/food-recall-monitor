from __future__ import annotations

import unittest

import httpx

from agents.fetchers.crawler.discovery import collapse_repeated_path_segments, normalize_resolved_url
from agents.fetchers.crawler.source_discovery import (
    LinkCandidate,
    looks_like_detail_url,
    looks_like_listing_url,
    prefer_unfiltered_listing_urls,
    score_recall_candidate,
    select_heuristic_seed_urls,
    _filter_blocked_paths,
    _filter_detail_keywords,
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
    def test_prefers_observed_unfiltered_listing(self) -> None:
        selected = prefer_unfiltered_listing_urls(
            ["https://alerts.example.gov/news-alerts?type=allergy"],
            observed_urls=[
                "https://alerts.example.gov/news-alerts",
                "https://alerts.example.gov/news-alerts?type=allergy",
            ],
        )
        self.assertEqual(selected, ["https://alerts.example.gov/news-alerts"])

    def test_keeps_query_when_canonical_listing_was_not_observed(self) -> None:
        filtered = "https://example.gov/search?section=recalls"
        selected = prefer_unfiltered_listing_urls(
            [filtered],
            observed_urls=[filtered],
        )
        self.assertEqual(selected, [filtered])

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


class DetailKeywordFilterTests(unittest.TestCase):
    def test_rejects_blocked_paths_that_cover_seed_urls(self) -> None:
        filtered = _filter_blocked_paths(
            ["/categorie/", "/about", "/assets/"],
            seed_urls=["https://example.com/categorie/1"],
        )
        self.assertEqual(filtered, ["/about", "/assets/"])

    def test_rejects_keywords_that_match_seed_listing_urls(self) -> None:
        filtered = _filter_detail_keywords(
            ["/home_node.html", "/___", "/meldungen/"],
            seed_urls=["https://www.example.com/DE/Home/home_node.html"],
            child_links=[
                LinkCandidate(
                    url="https://www.example.com/___example.com/Meldungen/2026/item.html",
                    anchor_text="item",
                    score=1,
                )
            ],
        )
        self.assertNotIn("/home_node.html", filtered)
        self.assertIn("/___", filtered)
        self.assertIn("/meldungen/", filtered)

    def test_rejects_keywords_absent_from_child_links(self) -> None:
        filtered = _filter_detail_keywords(
            ["/fiche-rappel/", "/___", "/meldungen/"],
            seed_urls=["https://www.example.com/DE/Home/home_node.html"],
            child_links=[
                LinkCandidate(
                    url="https://www.example.com/___example.com/Meldungen/2026/item.html",
                    anchor_text="item",
                    score=1,
                )
            ],
        )
        self.assertNotIn("/fiche-rappel/", filtered)
        self.assertIn("/___", filtered)

    def test_portal_detail_urls_are_recognized(self) -> None:
        self.assertTrue(
            looks_like_detail_url(
                "https://www.lebensmittelwarnung.de/___lebensmittelwarnung.de/Meldungen/2026/07_Juli/item.html"
            )
        )

    def test_infer_keywords_from_observed_detail_links(self) -> None:
        from agents.fetchers.crawler.source_discovery import _infer_keywords_from_links

        german_links = [
            LinkCandidate(
                url="https://www.lebensmittelwarnung.de/___lebensmittelwarnung.de/Meldungen/2026/a.html",
                anchor_text="a",
                score=1,
            ),
            LinkCandidate(
                url="https://www.lebensmittelwarnung.de/___lebensmittelwarnung.de/Meldungen/2026/b.html",
                anchor_text="b",
                score=1,
            ),
        ]
        french_links = [
            LinkCandidate(
                url="https://rappel.conso.gouv.fr/fiche-rappel/22774/Interne",
                anchor_text="product",
                score=1,
            ),
            LinkCandidate(
                url="https://rappel.conso.gouv.fr/fiche-rappel/22775/Interne",
                anchor_text="product 2",
                score=1,
            ),
        ]
        german = _infer_keywords_from_links(german_links)
        french = _infer_keywords_from_links(french_links)
        self.assertTrue(any("meldungen" in item or item.startswith("/___") for item in german))
        self.assertIn("/fiche-rappel/", french)

    def test_detail_pattern_ranking_prefers_notice_links(self) -> None:
        from agents.fetchers.crawler.source_discovery import (
            rank_detail_pattern_candidates,
            score_detail_pattern_candidate,
        )

        listing = LinkCandidate(
            url="https://example.com/recalls",
            anchor_text="Recalls",
            score=score_recall_candidate("https://example.com/recalls", "Recalls"),
        )
        detail = LinkCandidate(
            url="https://example.com/fiche-rappel/123",
            anchor_text="Milk",
            score=score_recall_candidate("https://example.com/fiche-rappel/123", "Milk"),
        )
        ranked = rank_detail_pattern_candidates([listing, detail], limit=2)
        self.assertEqual(ranked[0].url, detail.url)
        self.assertGreater(
            score_detail_pattern_candidate(detail.url, detail.anchor_text),
            score_detail_pattern_candidate(listing.url, listing.anchor_text),
        )


if __name__ == "__main__":
    unittest.main()
