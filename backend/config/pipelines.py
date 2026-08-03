"""Pipeline enablement switches loaded from ``pipelines.yaml``.

Controls whether the official recall pipeline and early-warning discovery
run, and whether empty-DB bootstrap runs at startup.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from settings import get_backend_root


class _StrictConfigModel(BaseModel):
    """Pydantic base that forbids unexpected YAML keys."""

    model_config = ConfigDict(extra="forbid")


class OfficialPipelineSwitch(_StrictConfigModel):
    """Enablement flags for the official food-recall pipeline.

    Attributes:
        enabled: When False, skip official pipeline runs and scheduling.
        bootstrap_on_empty_db: When True and the alerts DB is empty, run once
            at application startup.
    """

    enabled: bool = True
    bootstrap_on_empty_db: bool = True


class EarlyWarningSwitch(_StrictConfigModel):
    """Enablement flags for early-warning discovery.

    Attributes:
        enabled: When False, skip early-warning runs and scheduling.
        bootstrap_on_empty_db: When True and the incidents DB is empty, run
            one discovery pass at startup.
    """

    enabled: bool = False
    # When true and the incidents DB is empty, run one discovery pass at startup.
    bootstrap_on_empty_db: bool = True


class PipelineSwitches(_StrictConfigModel):
    """Top-level pipeline switch document from ``pipelines.yaml``.

    Attributes:
        official_pipeline: Official recall pipeline switches.
        early_warning: Early-warning discovery switches.
    """

    official_pipeline: OfficialPipelineSwitch = Field(default_factory=OfficialPipelineSwitch)
    early_warning: EarlyWarningSwitch = Field(default_factory=EarlyWarningSwitch)


# Default path to pipelines.yaml under the backend package
DEFAULT_PIPELINE_SWITCHES_PATH = get_backend_root() / "config" / "pipelines.yaml"


def load_pipeline_switches(path: str | Path | None = None) -> PipelineSwitches:
    """Load and validate pipeline switches from YAML.

    Args:
        path: Optional path to ``pipelines.yaml``. Relative paths are resolved
            against the backend root. Defaults to
            ``DEFAULT_PIPELINE_SWITCHES_PATH``.

    Returns:
        Validated ``PipelineSwitches`` model.

    Raises:
        ValueError: If the YAML root is not a mapping.
    """
    config_path = Path(path) if path is not None else DEFAULT_PIPELINE_SWITCHES_PATH
    if not config_path.is_absolute():
        config_path = get_backend_root() / config_path
    with config_path.open("r", encoding="utf-8") as config_file:
        payload = yaml.safe_load(config_file)
    if not isinstance(payload, dict):
        raise ValueError(f"pipeline switches config must be a mapping: {config_path}")
    return PipelineSwitches.model_validate(payload)
