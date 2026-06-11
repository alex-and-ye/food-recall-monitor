from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.food_recall_alert import FoodRecallAlertCreate


@dataclass
class FetchSourcesResult:
    records: list
    failures: dict[str, str] = field(default_factory=dict)


@dataclass
class AgentPipelineResult:
    alerts: list[FoodRecallAlertCreate]
    records_fetched: int
    source_failures: dict[str, str] = field(default_factory=dict)


@dataclass
class PipelineRunResult:
    new_alerts_count: int
    records_fetched: int
    source_failures: dict[str, str] = field(default_factory=dict)
