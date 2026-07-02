from __future__ import annotations

import os
import logging
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent
_DEFAULT_RUN_LOGS_DIR = _BACKEND_ROOT.parent / "pipeline_runs"
_RUN_LOGS_DIR_ENV_VAR = "BACKEND_RUN_LOGS_DIR"

_CONFIGURED = False


def configure_logging(level: int = logging.INFO) -> Path:
    global _CONFIGURED

    root_logger = logging.getLogger()
    if _CONFIGURED:
        return get_run_logs_dir()

    # Remove legacy backend file handlers so pipeline runs write only
    # to per-run files under pipeline_runs/.
    for handler in list(root_logger.handlers):
        if getattr(handler, "_backend_file_handler", False):
            root_logger.removeHandler(handler)
            try:
                handler.close()
            except OSError:
                pass

    root_logger.setLevel(level)

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(logger_name).setLevel(level)

    _CONFIGURED = True
    return get_run_logs_dir()


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
