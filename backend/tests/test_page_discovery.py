import unittest

from agents.fetchers.crawler.discovery import classify_page


class PageDiscoveryTests(unittest.TestCase):
    def test_classify_detail_page(self) -> None:
        html = "<html><title>Food recall alert</title><body>Recall risk and consumer action.</body></html>"
        page_class = classify_page(
            url="https://example.com/recalls/notice-1",
            html=html,
            recall_keywords=["recall", "alert"],
        )
        self.assertEqual(page_class, "detail")

    def test_classify_listing_page(self) -> None:
        html = "<html><body>" + ("<a href='/recalls/1'>Recall</a>" * 15) + "</body></html>"
        page_class = classify_page(
            url="https://example.com/recalls",
            html=html,
            recall_keywords=["recall"],
        )
        self.assertEqual(page_class, "listing")

    def test_classify_irrelevant_page(self) -> None:
        html = "<html><title>About us</title><body>Our history and team.</body></html>"
        page_class = classify_page(
            url="https://example.com/about",
            html=html,
            recall_keywords=["recall"],
        )
        self.assertEqual(page_class, "irrelevant")


if __name__ == "__main__":
    unittest.main()
