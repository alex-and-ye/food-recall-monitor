"""Application settings loaded from environment and optional ``.env``.

Provides a cached ``BackendSettings`` instance and the backend package root
path used to resolve relative config and data directories.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Absolute path to the backend package directory
_BACKEND_ROOT = Path(__file__).resolve().parent


class BackendSettings(BaseSettings):
    """Environment-backed configuration for the FastAPI backend.

    Attributes:
        chroma_host: Hostname of the ChromaDB server.
        chroma_port: Port of the ChromaDB server.
        chroma_server_data_path: Optional override for Chroma on-disk data.
        brave_api_key: API key for Brave Search (required when early warning
            is enabled).
        brave_search_base_url: Brave web search API base URL.
        early_warning_config_path: Optional path to ``early_warning.yaml``.
        pipeline_switches_path: Optional path to ``pipelines.yaml``.
    """

    model_config = SettingsConfigDict(
        env_file=_BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    chroma_host: str = "localhost"
    chroma_port: int = Field(default=8000, ge=1, le=65535)
    chroma_server_data_path: str | None = None
    brave_api_key: str | None = None
    brave_search_base_url: str = "https://api.search.brave.com/res/v1/web/search"
    early_warning_config_path: str | None = None
    pipeline_switches_path: str | None = None


@lru_cache
def get_settings() -> BackendSettings:
    """Return the process-wide cached settings instance.

    Returns:
        Parsed ``BackendSettings`` from env / ``.env``.
    """
    return BackendSettings()


def get_backend_root() -> Path:
    """Return the absolute path to the backend package directory.

    Returns:
        Path of the directory containing this module.
    """
    return _BACKEND_ROOT
