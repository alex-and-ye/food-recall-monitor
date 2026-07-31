import unittest

from agents.fetchers.extraction.cleaning import clean_detail_payload

class CleaningTests(unittest.TestCase):
    def test_cleaning_removes_html_and_tracking_params(self) -> None:
        payload = {
            "source_url": "https://example.com/recall?id=1&utm_source=newsletter",
            "headings": ["<h2>Risk</h2>", "<h2>Action</h2>"],
            "visible_text": "<p>Main text.</p><div>Cookie settings</div>",
            "published_date_candidates": ["2026-06-23", "2026-06-24"],
            "published_date_candidate_sources": {
                "2026-06-23": "selector",
                "2026-06-24": "generic",
            },
            "selected_recall_date": "2026-06-23",
            "selected_recall_date_source": "selector",
        }

        cleaned = clean_detail_payload(payload)
        self.assertEqual(cleaned["source_url"], "https://example.com/recall?id=1")
        self.assertNotIn("title", cleaned)
        self.assertEqual(cleaned["headings"], ["Risk", "Action"])
        self.assertNotIn("<", cleaned["visible_text"])
        self.assertNotIn("cookie", cleaned["visible_text"].lower())
        self.assertEqual(cleaned["selected_recall_date"], "2026-06-23")
        self.assertEqual(cleaned["selected_recall_date_source"], "selector")
        self.assertNotIn("published_date_candidates", cleaned)
        self.assertNotIn("published_date_candidate_sources", cleaned)

if __name__ == "__main__":
    unittest.main()
