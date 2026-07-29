from __future__ import annotations

from pathlib import Path

from settings import get_backend_root, get_settings


def get_chroma_server_data_path() -> Path:
    return _resolve_backend_path(
        get_settings().chroma_server_data_path,
        ".chroma_data",
    )


def _resolve_backend_path(raw_path: str | None, default_relative: str) -> Path:
    backend_root = get_backend_root()
    if raw_path:
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            candidate = (backend_root / candidate).resolve()
        return candidate
    return (backend_root / default_relative).resolve()


def ensure_backend_data_dirs() -> None:
    get_chroma_server_data_path().mkdir(parents=True, exist_ok=True)
