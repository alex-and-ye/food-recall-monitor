from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel, Field, field_validator

_source_names_provider: Callable[[], list[str]] | None = None


def set_source_names_provider(provider: Callable[[], list[str]] | None) -> None:
    global _source_names_provider
    _source_names_provider = provider


class PipelineRunOptions(BaseModel):
    sources: list[str] = Field(default_factory=lambda: list(_source_names()))
    limit: int = Field(default=10, ge=1, le=100)

    @field_validator("sources")
    @classmethod
    def validate_sources(cls, sources: list[str]) -> list[str]:
        configured_sources = set(_source_names())
        unknown_sources = sorted(set(sources).difference(configured_sources))
        if unknown_sources:
            raise ValueError(
                "Unknown source(s): "
                f"{', '.join(unknown_sources)}. "
                f"Configured sources: {', '.join(sorted(configured_sources))}"
            )
        return sources


def _source_names() -> list[str]:
    if _source_names_provider is not None:
        try:
            names = _source_names_provider()
            if names:
                return names
        except Exception:
            pass

    from config.sources import BOOTSTRAP_SOURCE_NAMES

    return list(BOOTSTRAP_SOURCE_NAMES)
