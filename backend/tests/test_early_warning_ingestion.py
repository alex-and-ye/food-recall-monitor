import unittest
from datetime import UTC, datetime
from unittest.mock import patch

import httpx

from agents.fetchers.rendering.static_fetch import StaticPage
from services.early_warning.ingestion import (
    EarlyWarningIngestionError,
    UnsupportedContentError,
    _preferred_publication_date,
    ingest_early_warning_url,
)


class EarlyWarningIngestionTests(unittest.IsolatedAsyncioTestCase):
    async def test_static_html_produces_provenance_and_content_hash(self) -> None:
        html = """
        <html lang="en"><head><title>Cheese safety warning</title></head>
        <body><main><h1>Cheese safety warning</h1>
        <time datetime="2026-07-20"></time>
        <p>A company is withdrawing cheese after possible Listeria contamination.</p>
        </main></body></html>
        """

        async def static_fetcher(*_args, **_kwargs):
            return StaticPage(
                html=html,
                final_url="https://example.test/story?utm_source=search",
                content_type="text/html",
            )

        async def browser_fetcher(*_args, **_kwargs):
            self.fail("browser fallback should not run")

        async with httpx.AsyncClient() as client:
            record = await ingest_early_warning_url(
                "https://example.test/story",
                client=client,
                minimum_text_characters=20,
                static_fetcher=static_fetcher,
                browser_fetcher=browser_fetcher,
            )

        self.assertEqual(record.payload["canonical_url"], "https://example.test/story")
        self.assertEqual(record.payload["publication_date"], "2026-07-20")
        self.assertEqual(len(record.payload["content_hash"]), 64)
        self.assertEqual(record.payload["provenance"]["discovery_method"], "arbitrary_url")

    async def test_rejects_non_html_content(self) -> None:
        async def static_fetcher(*_args, **_kwargs):
            return StaticPage("binary", "https://example.test/file.pdf", "application/pdf")

        async with httpx.AsyncClient() as client:
            with self.assertRaises(UnsupportedContentError) as context:
                await ingest_early_warning_url(
                    "https://example.test/file.pdf",
                    client=client,
                    static_fetcher=static_fetcher,
                )

        self.assertEqual(context.exception.content_type, "application/pdf")
        self.assertIsInstance(context.exception, EarlyWarningIngestionError)

    def test_preferred_publication_date_rejects_future_candidates(self) -> None:
        fixed_now = datetime(2026, 7, 23, 12, 0, tzinfo=UTC)

        with patch(
            "agents.fetchers.extraction.date_candidates.datetime"
        ) as mocked_datetime:
            mocked_datetime.now.return_value = fixed_now
            mocked_datetime.fromisoformat.side_effect = datetime.fromisoformat
            selected = _preferred_publication_date(
                {
                    "published_date_candidates": [
                        "2027-12-08",
                        "2026-07-18",
                        "2026-07-31",
                    ],
                    "published_date_candidate_sources": {
                        "2027-12-08": "structured",
                        "2026-07-18": "generic",
                        "2026-07-31": "selector",
                    },
                }
            )

        self.assertEqual(selected, "2026-07-18")


if __name__ == "__main__":
    unittest.main()
