"""Filesystem path helpers for backend data directories.

Resolves configured or default paths under the backend root and ensures
required data directories exist at startup.
"""

from pathlib import Path

from settings import get_backend_root, get_settings


def get_chroma_server_data_path() -> Path:
    """Return the resolved Chroma server data directory path.

    Uses ``chroma_server_data_path`` from settings when set; otherwise
    defaults to ``.chroma_data`` under the backend root.

    Returns:
        Absolute path to the Chroma data directory.
    """
    return _resolve_backend_path(
        get_settings().chroma_server_data_path,
        ".chroma_data",
    )


def _resolve_backend_path(raw_path: str | None, default_relative: str) -> Path:
    """Resolve a path relative to the backend root, or use a default.

    Args:
        raw_path: Optional configured path (absolute or relative). When
            relative, it is joined with the backend root.
        default_relative: Relative path under the backend root used when
            ``raw_path`` is unset.

    Returns:
        Absolute, resolved filesystem path.
    """
    backend_root = get_backend_root()
    if raw_path:
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            candidate = (backend_root / candidate).resolve()
        return candidate
    return (backend_root / default_relative).resolve()


def ensure_backend_data_dirs() -> None:
    """Create backend data directories if they do not already exist.

    Currently ensures the Chroma server data path is present.
    """
    get_chroma_server_data_path().mkdir(parents=True, exist_ok=True)
