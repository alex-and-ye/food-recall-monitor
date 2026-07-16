from __future__ import annotations

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
        async with async_playwright() as p:
            launch_kwargs = {"headless": True}
            if proxy_url:
                launch_kwargs["proxy"] = {"server": proxy_url}
            browser = await p.chromium.launch(**launch_kwargs)
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
    except NotImplementedError as exc:
        # Common on Windows under uvicorn's ProactorEventLoop / reload worker.
        raise RuntimeError(
            "Playwright browser fallback is unavailable in this event loop "
            f"(NotImplementedError). URL={url}"
        ) from exc
    except Exception as exc:
        raise RuntimeError(f"Playwright browser fetch failed for {url}: {exc}") from exc

    return html, final_url
