from datetime import UTC, datetime
import unittest

from agents.fetchers.extraction.date_candidates import (
    extract_date_candidates,
    select_recent_recall_date,
)


class DateCandidatesTests(unittest.TestCase):
    def test_extract_date_candidates_returns_iso_dates(self) -> None:
        candidates = extract_date_candidates("Recall issued on 23 June 2026 and updated 24 June 2026.")
        self.assertIn("2026-06-23", candidates)
        self.assertIn("2026-06-24", candidates)

    def test_extract_date_candidates_excludes_non_issued_page_dates(self) -> None:
        candidates = extract_date_candidates(
            "Allergy Alert, 4 June 2026 00:00. "
            "Product Details Best before 06 June 2026. "
            "Last modified: 17 June 2026 15:30. "
            "Prev : Earlier alert 18 June 2026. "
            "Next : Later alert 19 June 2026."
        )

        self.assertIn("2026-06-04", candidates)
        self.assertNotIn("2026-06-06", candidates)
        self.assertNotIn("2026-06-17", candidates)
        self.assertNotIn("2026-06-18", candidates)
        self.assertNotIn("2026-06-19", candidates)

    def test_select_recent_recall_date_respects_lookback(self) -> None:
        selected = select_recent_recall_date(
            ["2026-06-23", "2026-06-20"],
            lookback_days=1,
            now=datetime(2026, 6, 23, 12, 0, tzinfo=UTC),
        )
        self.assertEqual(selected, "2026-06-23")

    def test_select_recent_recall_date_returns_none_when_all_old(self) -> None:
        selected = select_recent_recall_date(
            ["2026-06-18", "2026-06-19"],
            lookback_days=1,
            now=datetime(2026, 6, 23, 12, 0, tzinfo=UTC),
        )
        self.assertIsNone(selected)


if __name__ == "__main__":
    unittest.main()
