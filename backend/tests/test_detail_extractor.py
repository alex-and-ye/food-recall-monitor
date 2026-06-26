import unittest

from agents.fetchers.extraction.detail_extractor import extract_detail_payload


class DetailExtractorTests(unittest.TestCase):
    def test_detail_extractor_returns_expected_fields(self) -> None:
        html = """
        <html>
          <head><title>Recall title</title></head>
          <body>
            <h1>Recall heading</h1>
            <h2>Risk</h2>
            <p>Published 23 June 2026. Do not consume product.</p>
          </body>
        </html>
        """

        payload = extract_detail_payload(source_url="https://example.com/recalls/1", html=html)
        self.assertEqual(payload["source_url"], "https://example.com/recalls/1")
        self.assertIn("Recall heading", payload["title"])
        self.assertTrue(payload["headings"])
        self.assertIn("Do not consume", payload["visible_text"])
        self.assertIn("2026-06-23", payload["published_date_candidates"])

    def test_detail_extractor_uses_main_content_only_when_available(self) -> None:
        html = """
        <html>
          <head><title>Recall title</title></head>
          <body>
            <header>Top navigation and login links</header>
            <main>
              <h1>Main recall heading</h1>
              <p>Published 24 June 2026. Stop using this product.</p>
            </main>
            <footer>Privacy policy and terms</footer>
          </body>
        </html>
        """

        payload = extract_detail_payload(source_url="https://example.com/recalls/2", html=html)
        self.assertIn("Main recall heading", payload["title"])
        self.assertIn("Stop using this product", payload["visible_text"])
        self.assertNotIn("Top navigation", payload["visible_text"])
        self.assertNotIn("Privacy policy", payload["visible_text"])


if __name__ == "__main__":
    unittest.main()
