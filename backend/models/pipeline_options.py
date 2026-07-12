from pydantic import BaseModel, Field, field_validator

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
    try:
        from dependencies import get_source_config_db

        names = get_source_config_db().list_source_names()
        if names:
            return names
    except Exception:
        pass

    from config.agents import BOOTSTRAP_SOURCE_NAMES

    return list(BOOTSTRAP_SOURCE_NAMES)
