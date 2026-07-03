from __future__ import annotations

import os
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent

_CHROMA_DATA_DIR_ENV = "CHROMA_DATA_DIR"
_RUN_LOGS_DIR_ENV = "BACKEND_RUN_LOGS_DIR"


def get_backend_root() -> Path:
    return _BACKEND_ROOT


def get_chroma_data_dir() -> Path:
    raw_path = os.getenv(_CHROMA_DATA_DIR_ENV)
    if raw_path:
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            candidate = (_BACKEND_ROOT / candidate).resolve()
    else:
        candidate = _BACKEND_ROOT / ".chroma_data"
    return candidate


def get_run_logs_dir() -> Path:
    raw_path = os.getenv(_RUN_LOGS_DIR_ENV)
    if raw_path:
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            candidate = (_BACKEND_ROOT / candidate).resolve()
    else:
        candidate = _BACKEND_ROOT / ".logs" / "pipeline_runs"
    return candidate


def ensure_backend_data_dirs() -> None:
    get_chroma_data_dir().mkdir(parents=True, exist_ok=True)
    get_run_logs_dir().mkdir(parents=True, exist_ok=True)
