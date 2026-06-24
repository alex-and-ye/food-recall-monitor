from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class ScraperHints(BaseModel):
    recall_keywords: list[str] = Field(default_factory=list)
    date_selectors: list[str] = Field(default_factory=list)
    blocked_paths: list[str] = Field(default_factory=list)
    force_browser: bool = False


class ScraperSourceConfig(BaseModel):
    base_url: str
    allowed_domains: list[str]
    seed_urls: list[str]
    max_depth: int = Field(default=1, ge=0, le=4)
    max_pages_per_run: int = Field(default=30, ge=1, le=500)
    lookback_days: int = Field(default=1, ge=1, le=7)
    hints: ScraperHints = Field(default_factory=ScraperHints)

    @field_validator("allowed_domains", mode="before")
    @classmethod
    def _normalize_domains(cls, value: list[str]) -> list[str]:
        return [str(domain).strip().lower() for domain in value if str(domain).strip()]

    @field_validator("seed_urls", mode="before")
    @classmethod
    def _normalize_seed_urls(cls, value: list[str]) -> list[str]:
        return [str(url).strip() for url in value if str(url).strip()]
