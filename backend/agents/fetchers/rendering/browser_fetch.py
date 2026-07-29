from __future__ import annotations

import asyncio
import logging

LOGGER = logging.getLogger(__name__)


async def fetch_browser_html(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    proxy_url: str | None = None,
    timeout_ms: int = 20_000,
) -> tuple[str, str]:
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
    """Run Playwright against a fresh event loop in a worker thread."""

    async def _runner() -> tuple[str, str]:
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
