from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_ROOT = Path(__file__).resolve().parent

class BackendSettings(BaseSettings):
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
    return BackendSettings()

def get_backend_root() -> Path:
    return _BACKEND_ROOT
