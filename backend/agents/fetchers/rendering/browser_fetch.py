from __future__ import annotations


async def fetch_browser_html(
    url: str,
    *,
    timeout_ms: int = 20_000,
) -> tuple[str, str]:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is not installed. Add playwright dependency.") from exc

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle", timeout=timeout_ms)
        html = await page.content()
        final_url = page.url
        await browser.close()
    return html, final_url
