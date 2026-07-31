from dataclasses import dataclass

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

@dataclass(frozen=True)
class StaticPage:
    html: str
    final_url: str
    content_type: str

async def fetch_static_html(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    proxy_url: str | None = None,
) -> tuple[str, str]:
    page = await fetch_static_page(
        client,
        url,
        headers=headers,
        proxy_url=proxy_url,
    )
    return page.html, page.final_url

@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=3),
    retry=retry_if_exception_type(httpx.HTTPError),
)
async def fetch_static_page(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    proxy_url: str | None = None,
) -> StaticPage:
    if proxy_url:
        async with httpx.AsyncClient(
            timeout=client.timeout,
            follow_redirects=True,
            proxy=proxy_url,
        ) as proxy_client:
            response = await proxy_client.get(url, headers=headers)
    else:
        response = await client.get(url, headers=headers)
    response.raise_for_status()
    return StaticPage(
        html=response.text,
        final_url=str(response.url),
        content_type=response.headers.get("content-type", "").split(";", 1)[0].strip().lower(),
    )
