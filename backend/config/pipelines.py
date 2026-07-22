from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from settings import get_backend_root


class _StrictConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OfficialPipelineSwitch(_StrictConfigModel):
    enabled: bool = True
    bootstrap_on_empty_db: bool = True


class EarlyWarningSwitch(_StrictConfigModel):
    enabled: bool = False
    # When true and the incidents DB is empty, run one discovery pass at startup.
    bootstrap_on_empty_db: bool = True


class PipelineSwitches(_StrictConfigModel):
    official_pipeline: OfficialPipelineSwitch = Field(default_factory=OfficialPipelineSwitch)
    early_warning: EarlyWarningSwitch = Field(default_factory=EarlyWarningSwitch)


DEFAULT_PIPELINE_SWITCHES_PATH = get_backend_root() / "config" / "pipelines.yaml"


def load_pipeline_switches(path: str | Path | None = None) -> PipelineSwitches:
    config_path = Path(path) if path is not None else DEFAULT_PIPELINE_SWITCHES_PATH
    if not config_path.is_absolute():
        config_path = get_backend_root() / config_path
    with config_path.open("r", encoding="utf-8") as config_file:
        payload = yaml.safe_load(config_file)
    if not isinstance(payload, dict):
        raise ValueError(f"pipeline switches config must be a mapping: {config_path}")
    return PipelineSwitches.model_validate(payload)
