from __future__ import annotations

import unittest

from config.early_warning import load_early_warning_config
from models.discovery_candidate import CandidateDecision
from models.search_candidate import SearchCandidate, canonicalize_url
from services.early_warning.candidate_filter import CandidateFilter


def _candidate(
    *,
    title: str,
    url: str,
    description: str = "",
    country: str = "GB",
    language: str = "en",
) -> SearchCandidate:
    return SearchCandidate(
        title=title,
        url=url,
        description=description,
        rank=1,
        query_id="query-1",
        query="food recall United Kingdom",
        country=country,
        language=language,
    )


class UrlCanonicalizationTests(unittest.TestCase):
    def test_normalizes_host_path_tracking_query_and_fragment(self) -> None:
        self.assertEqual(
            canonicalize_url(
                "HTTPS://BÜCHER.example:443/a/../Recall/?utm_medium=email&z=2&a=1#section"
            ),
            "https://xn--bcher-kva.example/Recall?a=1&z=2",
        )

    def test_rejects_non_web_and_credential_urls(self) -> None:
        with self.assertRaises(ValueError):
            canonicalize_url("javascript:alert(1)")
        with self.assertRaises(ValueError):
            canonicalize_url("https://user:pass@example.com/recall")


class CandidateFilterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.filter = CandidateFilter(load_early_warning_config())

    def test_accepts_strong_official_recall_candidate(self) -> None:
        result = self.filter.evaluate(
            _candidate(
                title="Food recall: unsafe cheese",
                url="https://www.food.gov.uk/news-alerts/alert/cheese-recall",
                description="A beverage and food safety alert for consumers.",
                country="GB",
            )
        )

        self.assertEqual(result.decision, CandidateDecision.ACCEPT)
        self.assertGreaterEqual(result.confidence, 0.68)
        self.assertTrue(any(reason.startswith("trusted domain:") for reason in result.reasons))

    def test_accepts_hyphenated_news_recall_url(self) -> None:
        result = self.filter.evaluate(
            _candidate(
                title="Waitrose warns customers of unsafe food in urgent recall notice",
                url="https://www.glasgowlive.co.uk/whats-on/food-drink-news/waitrose-food-recall-notice-warning-34332452",
                description="Shoppers have been told not to eat the product.",
                country="GB",
            )
        )

        self.assertEqual(result.decision, CandidateDecision.ACCEPT)
        self.assertTrue(any("food recall" in reason for reason in result.reasons))

    def test_marks_partial_signal_as_borderline(self) -> None:
        result = self.filter.evaluate(
            _candidate(
                title="Food recall announced",
                url="https://news.example/article/123",
                description="Food product details.",
                country="GB",
            )
        )

        self.assertEqual(result.decision, CandidateDecision.BORDERLINE)

    def test_rejects_weak_and_excluded_candidates(self) -> None:
        weak = self.filter.evaluate(
            _candidate(
                title="Weekly market report",
                url="https://news.example/article/123",
                description="Prices increased.",
                country="GB",
            )
        )
        excluded = self.filter.evaluate(
            _candidate(
                title="Food recall",
                url="https://facebook.com/posts/1",
                description="Food safety alert.",
                country="GB",
            )
        )

        self.assertEqual(weak.decision, CandidateDecision.REJECT)
        self.assertEqual(excluded.decision, CandidateDecision.REJECT)
        self.assertEqual(excluded.confidence, 0.0)
        self.assertEqual(excluded.reasons, ["excluded domain: facebook.com"])

    def test_rejects_non_food_electronics_recall_before_fetching(self) -> None:
        result = self.filter.evaluate(
            _candidate(
                title="Electronics recall: unsafe battery charger",
                url="https://news.example/electronics-recall-charger",
                description="Consumers should return the affected charger.",
                country="GB",
            )
        )

        self.assertEqual(result.decision, CandidateDecision.REJECT)
        self.assertEqual(result.confidence, 0.0)
        self.assertIn("excluded topic term: electronics", result.reasons)

    def test_filter_is_deterministic(self) -> None:
        candidate = _candidate(
            title="Food recall announced",
            url="https://news.example/article/123",
            description="Food product details.",
            country="GB",
        )

        first = self.filter.evaluate(candidate)
        second = self.filter.evaluate(candidate)

        self.assertEqual(first.decision, second.decision)
        self.assertEqual(first.confidence, second.confidence)
        self.assertEqual(first.reasons, second.reasons)


if __name__ == "__main__":
    unittest.main()
