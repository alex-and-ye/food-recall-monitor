import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

from config.early_warning import BraveSearchConfig
from models.search_candidate import SearchCandidate, SearchQuery, SearchResponse

BRAVE_WEB_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
_RETRYABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
SleepCallable = Callable[[float], Awaitable[None]]

class BraveSearchError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code

class BraveSearchClient:
    def __init__(
        self,
        api_key: str,
        *,
        config: BraveSearchConfig | None = None,
        client: httpx.AsyncClient | None = None,
        sleep: SleepCallable = asyncio.sleep,
        random_source: random.Random | None = None,
        base_url: str = BRAVE_WEB_SEARCH_URL,
    ) -> None:
        normalized_key = api_key.strip()
        if not normalized_key:
            raise ValueError("BRAVE_API_KEY must be non-empty")
        self._api_key = normalized_key
        self._config = config or BraveSearchConfig()
        self._client = client or httpx.AsyncClient(timeout=self._config.timeout_seconds)
        self._owns_client = client is None
        self._sleep = sleep
        self._random = random_source or random.Random()
        self._base_url = base_url.strip()
        if not self._base_url:
            raise ValueError("Brave Search base URL must be non-empty")
        self._pace_lock = asyncio.Lock()
        self._last_request_at: float | None = None

    async def __aenter__(self) -> BraveSearchClient:
        return self

    async def __aexit__(self, *_args: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def search(
        self,
        query: SearchQuery,
        *,
        count: int = 10,
        offset: int = 0,
        freshness: str | None = None,
    ) -> SearchResponse:
        if not 1 <= count <= 20:
            raise ValueError("count must be between 1 and 20")
        if not 0 <= offset <= 9:
            raise ValueError("offset must be between 0 and 9")
        effective_freshness = BraveSearchConfig(
            freshness=freshness or self._config.freshness
        ).freshness
        params = {
            "q": query.text,
            "count": count,
            "offset": offset,
            "freshness": effective_freshness,
            "country": query.country.lower(),
            "search_lang": query.language,
            "safesearch": "moderate",
        }
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self._api_key,
        }

        response: httpx.Response | None = None
        for attempt in range(self._config.max_retries + 1):
            try:
                await self._pace_request()
                response = await self._client.get(
                    self._base_url,
                    params=params,
                    headers=headers,
                )
            except httpx.RequestError as exc:
                if attempt >= self._config.max_retries:
                    raise BraveSearchError("Brave Search request failed after retries") from exc
                await self._sleep(self._retry_delay(attempt, None))
                self._last_request_at = None
                continue

            if response.status_code < 400:
                return self._normalize_response(response, query=query, offset=offset)
            if response.status_code in {401, 403}:
                raise BraveSearchError(
                    "Brave Search rejected the API credential",
                    status_code=response.status_code,
                )
            if (
                response.status_code not in _RETRYABLE_STATUS_CODES
                or attempt >= self._config.max_retries
            ):
                raise BraveSearchError(
                    f"Brave Search returned HTTP {response.status_code}",
                    status_code=response.status_code,
                )
            await self._sleep(self._retry_delay(attempt, response))
            self._last_request_at = None

        raise BraveSearchError("Brave Search request failed")

    async def _pace_request(self) -> None:
        minimum_interval = self._config.minimum_interval_seconds
        if minimum_interval <= 0:
            return
        async with self._pace_lock:
            now = time.monotonic()
            if self._last_request_at is not None:
                delay = minimum_interval - (now - self._last_request_at)
                if delay > 0:
                    await self._sleep(delay)
            self._last_request_at = time.monotonic()

    def _retry_delay(self, attempt: int, response: httpx.Response | None) -> float:
        if response is not None and response.status_code == 429:
            header_delay = _rate_limit_delay(response.headers)
            if header_delay is not None:
                return header_delay
        exponential = self._config.backoff_seconds * (2**attempt)
        jitter = self._random.uniform(0.0, self._config.jitter_seconds)
        return exponential + jitter

    @staticmethod
    def _normalize_response(
        response: httpx.Response,
        *,
        query: SearchQuery,
        offset: int,
    ) -> SearchResponse:
        try:
            payload = response.json()
        except ValueError as exc:
            raise BraveSearchError("Brave Search returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise BraveSearchError("Brave Search returned an invalid response")
        web = payload.get("web")
        web_payload = web if isinstance(web, dict) else {}
        raw_results = web_payload.get("results")
        results = raw_results if isinstance(raw_results, list) else []
        candidates: list[SearchCandidate] = []
        for rank, raw_result in enumerate(results, start=1):
            if not isinstance(raw_result, dict):
                continue
            title = str(raw_result.get("title") or "").strip()
            url = str(raw_result.get("url") or "").strip()
            if not title or not url:
                continue
            try:
                candidate = SearchCandidate(
                    title=title,
                    url=url,
                    description=str(raw_result.get("description") or "").strip(),
                    age=_optional_text(raw_result.get("age")),
                    page_age=_parse_page_age(raw_result.get("page_age")),
                    rank=rank,
                    query_id=query.query_id,
                    query=query.text,
                    country=query.country,
                    language=query.language,
                )
            except ValueError:
                continue
            candidates.append(candidate)
        total_count = _optional_non_negative_int(web_payload.get("estimated_count"))
        query_payload = payload.get("query")
        more_results_available = bool(
            query_payload.get("more_results_available")
            if isinstance(query_payload, dict)
            else web_payload.get("more_results_available", False)
        )
        return SearchResponse(
            query=query,
            candidates=candidates,
            total_count=total_count,
            offset=offset,
            more_results_available=more_results_available,
        )

def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None

def _optional_non_negative_int(value: object) -> int | None:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None

def _parse_page_age(value: object) -> datetime | None:
    text = _optional_text(value)
    if text is None:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed

def _rate_limit_delay(headers: httpx.Headers) -> float | None:
    retry_after = headers.get("retry-after")
    if retry_after:
        try:
            return max(0.0, float(retry_after))
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(retry_after)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=timezone.utc)
                now = datetime.now(retry_at.tzinfo)
                return max(0.0, (retry_at - now).total_seconds())
            except (TypeError, ValueError, OverflowError):
                pass
    reset = headers.get("x-ratelimit-reset")
    if reset:
        parsed_delays: list[float] = []
        for token in reset.split(","):
            try:
                raw_reset = float(token.strip())
            except ValueError:
                continue
            if raw_reset > 10_000_000_000:
                raw_reset /= 1000
            if raw_reset > 1_000_000_000:
                raw_reset -= datetime.now(timezone.utc).timestamp()
            parsed_delays.append(max(0.0, raw_reset))
        if parsed_delays:
            return min(parsed_delays)
    return None
