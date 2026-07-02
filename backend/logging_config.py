from __future__ import annotations

import os
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent
_DEFAULT_RUN_LOGS_DIR = _BACKEND_ROOT.parent / "pipeline_runs"
_RUN_LOGS_DIR_ENV_VAR = "BACKEND_RUN_LOGS_DIR"


def get_run_logs_dir() -> Path:
    raw_path = os.getenv(_RUN_LOGS_DIR_ENV_VAR)
    if raw_path:
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            candidate = (_BACKEND_ROOT / candidate).resolve()
    else:
        candidate = _DEFAULT_RUN_LOGS_DIR

    candidate.mkdir(parents=True, exist_ok=True)
    return candidate
