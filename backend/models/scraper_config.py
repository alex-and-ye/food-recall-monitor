from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

DEFAULT_DETAIL_PAGE_KEYWORDS: list[str] = [
    "/recall/",
    "/alert/",
    "/withdrawal/",
    "/notice/",
]
DEFAULT_MAX_DEPTH = 1
DEFAULT_MAX_PAGES_PER_RUN = 30
DEFAULT_LOOKBACK_DAYS = 1


class ScraperHints(BaseModel):
    detail_page_keywords: list[str] = Field(default_factory=lambda: list(DEFAULT_DETAIL_PAGE_KEYWORDS))
    date_selectors: list[str] = Field(default_factory=list)
    blocked_paths: list[str] = Field(default_factory=list)
    force_browser: bool = False

    @field_validator("detail_page_keywords", mode="before")
    @classmethod
    def _normalize_detail_page_keywords(cls, value: object) -> list[str]:
        if value is None:
            return list(DEFAULT_DETAIL_PAGE_KEYWORDS)
        if not isinstance(value, list):
            return list(DEFAULT_DETAIL_PAGE_KEYWORDS)
        normalized = [str(keyword).strip().lower() for keyword in value if str(keyword).strip()]
        return normalized or list(DEFAULT_DETAIL_PAGE_KEYWORDS)


class ScraperSourceConfig(BaseModel):
    base_url: str
    allowed_domains: list[str]
    seed_urls: list[str]
    request_headers: dict[str, str] = Field(default_factory=dict)
    proxy_url: str | None = None
    max_depth: int = Field(default=DEFAULT_MAX_DEPTH, ge=0, le=4)
    max_pages_per_run: int = Field(default=DEFAULT_MAX_PAGES_PER_RUN, ge=1, le=500)
    lookback_days: int = Field(default=DEFAULT_LOOKBACK_DAYS, ge=1, le=7)
    hints: ScraperHints = Field(default_factory=ScraperHints)

    @field_validator("allowed_domains", mode="before")
    @classmethod
    def _normalize_domains(cls, value: list[str]) -> list[str]:
        return [str(domain).strip().lower() for domain in value if str(domain).strip()]

    @field_validator("seed_urls", mode="before")
    @classmethod
    def _normalize_seed_urls(cls, value: list[str]) -> list[str]:
        return [str(url).strip() for url in value if str(url).strip()]

    @field_validator("request_headers", mode="before")
    @classmethod
    def _normalize_request_headers(cls, value: object) -> dict[str, str]:
        if not isinstance(value, dict):
            return {}
        return {
            str(key).strip(): str(header_value).strip()
            for key, header_value in value.items()
            if str(key).strip()
        }

    @field_validator("proxy_url", mode="before")
    @classmethod
    def _normalize_proxy_url(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("max_depth", mode="before")
    @classmethod
    def _normalize_max_depth(cls, value: object) -> int:
        if value is None:
            return DEFAULT_MAX_DEPTH
        return int(value)

    @field_validator("max_pages_per_run", mode="before")
    @classmethod
    def _normalize_max_pages_per_run(cls, value: object) -> int:
        if value is None:
            return DEFAULT_MAX_PAGES_PER_RUN
        return int(value)

    @field_validator("lookback_days", mode="before")
    @classmethod
    def _normalize_lookback_days(cls, value: object) -> int:
        if value is None:
            return DEFAULT_LOOKBACK_DAYS
        return int(value)

    @field_validator("hints", mode="before")
    @classmethod
    def _normalize_hints(cls, value: object) -> ScraperHints:
        if value is None:
            return ScraperHints()
        if isinstance(value, ScraperHints):
            return value
        if isinstance(value, dict):
            return ScraperHints(**value)
        return ScraperHints()
