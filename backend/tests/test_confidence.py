import unittest

from models.early_warning_incident import SourceKind
from services.early_warning.confidence import (
    SOURCE_KIND_BASE_WEIGHTS,
    calculate_confidence,
)


class ConfidenceTests(unittest.TestCase):
    def test_requested_source_kind_base_weights(self) -> None:
        expected = {
            SourceKind.OFFICIAL_RECALL: 100,
            SourceKind.GOVERNMENT_INVESTIGATION: 95,
            SourceKind.WHO_FAO: 90,
            SourceKind.COMPANY_RELEASE: 85,
            SourceKind.MAJOR_NEWS: 75,
            SourceKind.TRADE_PUBLICATION: 65,
            SourceKind.UNKNOWN: 40,
            SourceKind.BLOG: 20,
        }

        self.assertEqual(SOURCE_KIND_BASE_WEIGHTS, expected)

    def test_modifiers_are_bounded_and_auditable(self) -> None:
        result = calculate_confidence(
            SourceKind.MAJOR_NEWS,
            independent_source_count=4,
            has_product_evidence=True,
            has_hazard_evidence=True,
            has_date_evidence=True,
            trusted_domain_override=True,
        )

        self.assertEqual(result.score, 99)
        self.assertEqual(result.reasons[0], "source kind major_news: base 75")
        self.assertTrue(any("corroborating" in reason for reason in result.reasons))
        self.assertTrue(any("bounded" in reason for reason in result.reasons))

    def test_negative_modifiers_never_reduce_score_below_zero(self) -> None:
        result = calculate_confidence(
            SourceKind.BLOG,
            stale_reporting=True,
            vague_reporting=True,
        )

        self.assertEqual(result.score, 0)
        self.assertTrue(any("stale reporting" in reason for reason in result.reasons))
        self.assertTrue(any("vague reporting" in reason for reason in result.reasons))

    def test_official_match_sets_one_hundred(self) -> None:
        result = calculate_confidence(SourceKind.BLOG, official_match=True)

        self.assertEqual(result.score, 100)
        self.assertIn("official recall match", result.reasons[0])


if __name__ == "__main__":
    unittest.main()
