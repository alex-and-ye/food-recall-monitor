"""Headless browser HTML fetching via Playwright.

Loads recall source pages in Chromium when static HTTP fetching is insufficient,
with a thread-based fallback for event loops that cannot run async Playwright.
"""

import asyncio
import logging

# Module logger for Playwright event-loop fallback warnings.
LOGGER = logging.getLogger(__name__)


async def fetch_browser_html(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    proxy_url: str | None = None,
    timeout_ms: int = 20_000,
) -> tuple[str, str]:
    """Fetch page HTML using a headless Chromium browser.

    Args:
        url: Target page URL.
        headers: Optional HTTP headers applied to the browser context.
        proxy_url: Optional proxy server URL for browser launch.
        timeout_ms: Navigation timeout in milliseconds.

    Returns:
        A tuple of ``(html, final_url)`` after redirects and JavaScript execution.

    Raises:
        RuntimeError: If Playwright is not installed or the browser fetch fails.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is not installed. Add playwright dependency.") from exc

    try:
        return await _fetch_with_async_playwright(
            url,
            headers=headers,
            proxy_url=proxy_url,
            timeout_ms=timeout_ms,
        )
    except NotImplementedError:
        # Common on Windows under uvicorn's ProactorEventLoop / reload worker.
        LOGGER.warning(
            "Async Playwright unavailable in this event loop; retrying in a worker thread for %s",
            url,
        )
        return await asyncio.to_thread(
            _fetch_browser_html_sync,
            url,
            headers=headers,
            proxy_url=proxy_url,
            timeout_ms=timeout_ms,
        )


async def _fetch_with_async_playwright(
    url: str,
    *,
    headers: dict[str, str] | None,
    proxy_url: str | None,
    timeout_ms: int,
) -> tuple[str, str]:
    """Load a URL in async Playwright and return rendered HTML."""
    from playwright.async_api import async_playwright

    try:
        async with async_playwright() as playwright:
            launch_kwargs: dict[str, object] = {"headless": True}
            if proxy_url:
                launch_kwargs["proxy"] = {"server": proxy_url}
            browser = await playwright.chromium.launch(**launch_kwargs)
            browser_headers = dict(headers or {})
            user_agent = browser_headers.pop("User-Agent", None)
            context = await browser.new_context(
                user_agent=user_agent,
                extra_http_headers=browser_headers or None,
            )
            page = await context.new_page()
            await page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            html = await page.content()
            final_url = page.url
            await context.close()
            await browser.close()
    except NotImplementedError:
        raise
    except Exception as exc:
        raise RuntimeError(f"Playwright browser fetch failed for {url}: {exc}") from exc

    return html, final_url


def _fetch_browser_html_sync(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    proxy_url: str | None = None,
    timeout_ms: int = 20_000,
) -> tuple[str, str]:
    """Run Playwright against a fresh event loop in a worker thread.

    Args:
        url: Target page URL.
        headers: Optional HTTP headers applied to the browser context.
        proxy_url: Optional proxy server URL for browser launch.
        timeout_ms: Navigation timeout in milliseconds.

    Returns:
        A tuple of ``(html, final_url)`` from the browser fetch.

    Raises:
        RuntimeError: If the threaded Playwright fallback cannot complete.
    """

    async def _runner() -> tuple[str, str]:
        """Run the async Playwright fetch inside ``asyncio.run``."""
        return await _fetch_with_async_playwright(
            url,
            headers=headers,
            proxy_url=proxy_url,
            timeout_ms=timeout_ms,
        )

    try:
        return asyncio.run(_runner())
    except Exception as exc:
        raise RuntimeError(
            "Playwright browser fallback is unavailable in this event loop "
            f"({type(exc).__name__}). URL={url}"
        ) from exc
