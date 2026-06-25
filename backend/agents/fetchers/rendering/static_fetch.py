from __future__ import annotations

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=3),
    retry=retry_if_exception_type(httpx.HTTPError),
)
async def fetch_static_html(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    proxy_url: str | None = None,
) -> tuple[str, str]:
    response = await client.get(url, headers=headers, proxy=proxy_url)
    response.raise_for_status()
    return response.text, str(response.url)
