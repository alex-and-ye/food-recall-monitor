"""Pipeline run option models and source-name provider wiring.

Validates which configured sources a pipeline run may target and the
per-run record limit.
"""

from collections.abc import Callable

from pydantic import BaseModel, Field, field_validator

# Optional injectable provider of configured source names.
_source_names_provider: Callable[[], list[str]] | None = None

def set_source_names_provider(provider: Callable[[], list[str]] | None) -> None:
    """Register a callable that returns the list of configured source names.

    Args:
        provider: Zero-arg callable returning source names, or ``None`` to
            clear and fall back to bootstrap names.
    """
    global _source_names_provider
    _source_names_provider = provider

class PipelineRunOptions(BaseModel):
    """User-selectable options for an official pipeline run."""

    sources: list[str] = Field(default_factory=lambda: list(_source_names()))
    limit: int = Field(default=10, ge=1, le=100)

    @field_validator("sources")
    @classmethod
    def validate_sources(cls, sources: list[str]) -> list[str]:
        """Reject source names that are not in the configured registry.

        Args:
            sources: Requested source name list.

        Returns:
            The same list when all names are known.

        Raises:
            ValueError: If any source is not configured.
        """
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
    """Return configured source names via provider or bootstrap fallback."""
    if _source_names_provider is not None:
        try:
            names = _source_names_provider()
            if names:
                return names
        except Exception:
            pass

    from config.sources import BOOTSTRAP_SOURCE_NAMES

    return list(BOOTSTRAP_SOURCE_NAMES)
