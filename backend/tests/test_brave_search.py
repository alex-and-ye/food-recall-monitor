from __future__ import annotations

import unittest

import httpx

from config.early_warning import BraveSearchConfig
from models.search_candidate import SearchQuery
from services.early_warning.brave_search import BraveSearchClient, BraveSearchError


def _query() -> SearchQuery:
    return SearchQuery.create(
        text='"food recall" Canada',
        country="CA",
        language="en",
    )


class BraveSearchClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_normalizes_results_and_request_parameters(self) -> None:
        observed_request: httpx.Request | None = None

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal observed_request
            observed_request = request
            return httpx.Response(
                200,
                json={
                    "query": {"more_results_available": True},
                    "web": {
                        "estimated_count": 23,
                        "results": [
                            {
                                "title": " Food recall ",
                                "url": "HTTPS://Example.com:443/a/../recall/?utm_source=x&b=2&a=1#top",
                                "description": " Notice ",
                                "age": "2 hours ago",
                                "page_age": "2026-07-22T12:00:00Z",
                            },
                            {"title": "", "url": "https://example.com/ignored"},
                        ],
                    }
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = BraveSearchClient("key", client=http_client)
            response = await client.search(_query(), count=20, offset=9, freshness="pd")

        self.assertIsNotNone(observed_request)
        assert observed_request is not None
        self.assertEqual(observed_request.headers["x-subscription-token"], "key")
        self.assertEqual(observed_request.url.params["count"], "20")
        self.assertEqual(observed_request.url.params["offset"], "9")
        self.assertEqual(observed_request.url.params["freshness"], "pd")
        self.assertEqual(response.total_count, 23)
        self.assertEqual(len(response.candidates), 1)
        self.assertEqual(response.candidates[0].url, "https://example.com/recall?a=1&b=2")
        self.assertEqual(response.candidates[0].rank, 1)
        self.assertTrue(response.more_results_available)

    async def test_retries_429_and_honors_retry_after(self) -> None:
        calls = 0
        delays: list[float] = []

        async def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(429, headers={"Retry-After": "2.5"})
            return httpx.Response(200, json={"web": {"results": []}})

        async def record_sleep(delay: float) -> None:
            delays.append(delay)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = BraveSearchClient(
                "key",
                client=http_client,
                config=BraveSearchConfig(max_retries=1, jitter_seconds=0),
                sleep=record_sleep,
            )
            response = await client.search(_query())

        self.assertEqual(response.candidates, [])
        self.assertEqual(calls, 2)
        self.assertEqual(delays, [2.5])

    async def test_does_not_retry_authentication_failures(self) -> None:
        calls = 0

        async def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(401)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = BraveSearchClient(
                "bad-key",
                client=http_client,
                config=BraveSearchConfig(max_retries=3),
            )
            with self.assertRaises(BraveSearchError) as context:
                await client.search(_query())

        self.assertEqual(context.exception.status_code, 401)
        self.assertEqual(calls, 1)

    async def test_enforces_brave_pagination_limits(self) -> None:
        client = BraveSearchClient("key", client=httpx.AsyncClient())
        self.addAsyncCleanup(client._client.aclose)

        with self.assertRaises(ValueError):
            await client.search(_query(), count=21)
        with self.assertRaises(ValueError):
            await client.search(_query(), offset=10)


if __name__ == "__main__":
    unittest.main()
