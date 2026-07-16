from datetime import UTC, datetime
import unittest

from agents.fetchers.extraction.date_candidates import (
    extract_date_candidates,
    select_recent_recall_date,
)
from agents.fetchers.extraction.date_parser import (
    extract_structured_dates,
    infer_document_languages,
    search_adaptive_dates,
)
from agents.fetchers.extraction.detail_extractor import extract_detail_payload


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

    def test_search_adaptive_dates_handles_ambiguous_numeric_formats(self) -> None:
        reference = datetime(2026, 7, 3, 12, 0, tzinfo=UTC)
        candidates = search_adaptive_dates(
            "Recall published on 03/07/2026.",
            languages=["fr"],
            reference_date=reference,
        )

        self.assertIn("2026-07-03", candidates)
        self.assertIn("2026-03-07", candidates)

    def test_search_adaptive_dates_filters_implausible_years(self) -> None:
        reference = datetime(2026, 7, 3, 12, 0, tzinfo=UTC)
        candidates = search_adaptive_dates(
            "Category counts like Lait et produits laitiers (3204) should be ignored.",
            reference_date=reference,
        )

        self.assertFalse(any(candidate.startswith("3204-") for candidate in candidates))

    def test_infer_document_languages_prefers_html_lang(self) -> None:
        languages = infer_document_languages("fr-FR", configured_languages=["de"])
        self.assertEqual(languages, ["fr", "de"])

    def test_extract_structured_dates_normalizes_datetime_attributes(self) -> None:
        candidates = extract_structured_dates(["2026-07-03T10:15:00Z", "2026-07-03"])
        self.assertEqual(candidates, ["2026-07-03"])

    def test_extract_structured_dates_preserves_calendar_day(self) -> None:
        candidates = extract_structured_dates(
            [
                "2026-07-10T19:09:33",
                "2026-07-10T23:30:00-05:00",
            ]
        )
        self.assertEqual(candidates, ["2026-07-10"])

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

    def test_select_recent_recall_date_prefers_in_window_ambiguous_candidate(self) -> None:
        selected = select_recent_recall_date(
            ["2026-03-07", "2026-07-03"],
            lookback_days=1,
            now=datetime(2026, 7, 3, 12, 0, tzinfo=UTC),
        )
        self.assertEqual(selected, "2026-07-03")

    def test_select_recent_recall_date_prefers_source_and_document_order(self) -> None:
        selected = select_recent_recall_date(
            ["2026-07-10", "2026-07-12"],
            lookback_days=2,
            now=datetime(2026, 7, 12, 12, 0, tzinfo=UTC),
            candidate_sources={"2026-07-10": "structured", "2026-07-12": "selector"},
        )
        self.assertEqual(selected, "2026-07-10")

    def test_search_adaptive_dates_rejects_adjacent_date_fragments(self) -> None:
        reference = datetime(2026, 7, 12, 12, 0, tzinfo=UTC)
        candidates = search_adaptive_dates(
            "10.07.2026 08.07.2026 07.07.2026",
            languages=["de"],
            reference_date=reference,
        )
        self.assertIn("2026-07-10", candidates)
        self.assertIn("2026-07-08", candidates)
        self.assertNotIn("2026-07-12", candidates)

    def test_extract_structured_dates_accepts_localized_numeric_attributes(self) -> None:
        candidates = extract_structured_dates(["10.07.2026", "2026-07-03T10:15:00Z"])
        self.assertEqual(candidates, ["2026-07-10", "2026-07-03"])

    def test_detail_extractor_uses_html_lang_for_numeric_dates(self) -> None:
        html = """
        <html lang="fr">
          <body>
            <main>
              <h1>Recall heading</h1>
              <p>Published 03/07/2026.</p>
            </main>
          </body>
        </html>
        """

        payload = extract_detail_payload(source_url="https://example.com/recalls/fr", html=html)

        self.assertIn("2026-07-03", payload["published_date_candidates"])

    def test_detail_extractor_collects_structured_datetime_values(self) -> None:
        html = """
        <html lang="en">
          <body>
            <main>
              <h1>Recall heading</h1>
              <time datetime="2026-06-24T08:00:00Z">24 June 2026</time>
            </main>
          </body>
        </html>
        """

        payload = extract_detail_payload(
            source_url="https://example.com/recalls/structured",
            html=html,
            date_selectors=["time"],
        )

        self.assertEqual(payload["published_date_candidates"][0], "2026-06-24")
        self.assertEqual(payload["published_date_candidate_sources"]["2026-06-24"], "structured")


if __name__ == "__main__":
    unittest.main()
