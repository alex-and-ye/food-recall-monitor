"""Dataclass result types returned by pipeline stages.

Covers fetch outcomes, agent-produced alerts, and end-of-run summaries.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.food_recall_alert import FoodRecallAlertCreate
    from models.scraped_record import ScrapedRecallRecord

@dataclass
class FetchSourcesResult:
    """Outcome of fetching and scraping configured official sources."""

    records: list[ScrapedRecallRecord]
    failures: dict[str, str] = field(default_factory=dict)

@dataclass
class AgentPipelineResult:
    """Outcome of the agent phase that turns scraped records into alerts."""

    alerts: list[FoodRecallAlertCreate]
    records_fetched: int
    source_failures: dict[str, str] = field(default_factory=dict)

@dataclass
class PipelineRunResult:
    """Summary returned when an official pipeline run completes."""

    new_alerts_count: int
    records_fetched: int
    source_failures: dict[str, str] = field(default_factory=dict)
