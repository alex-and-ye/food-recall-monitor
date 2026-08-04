"""Service for emitting and managing pipeline warning records.

Wraps the warnings database with message truncation and convenience helpers
for listing, summarizing, and acknowledging operational warnings.
"""

from db.warnings_interface import PipelineWarningsDBInterface
from models.pipeline_warning import (
    MAX_WARNING_MESSAGE_LENGTH,
    PipelineWarning,
    PipelineWarningCreate,
    PipelineWarningsSummary,
    WarningCategory,
)


class WarningsService:
    """Create and manage pipeline operational warnings."""

    def __init__(self, db: PipelineWarningsDBInterface) -> None:
        """Initialize with a warnings database backend.

        Args:
            db: Database interface for warning persistence.
        """
        self.db = db

    def emit(
        self,
        *,
        category: WarningCategory,
        message: str,
        source: str | None = None,
        run_id: str | None = None,
    ) -> PipelineWarning:
        """Persist a new warning with a truncated message.

        Args:
            category: Warning category classification.
            message: Human-readable warning text.
            source: Optional source name associated with the warning.
            run_id: Optional pipeline run identifier.

        Returns:
            The created PipelineWarning record.
        """
        return self.db.create(
            PipelineWarningCreate(
                category=category,
                message=_truncate_message(message),
                source=source,
                run_id=run_id,
            )
        )

    def list_warnings(self, *, acknowledged: bool | None = None) -> list[PipelineWarning]:
        """List warnings, optionally filtered by acknowledgement state.

        Args:
            acknowledged: If True/False, filter by that state; None returns all.

        Returns:
            Matching warning records.
        """
        return self.db.list_warnings(acknowledged=acknowledged)

    def get_summary(self) -> PipelineWarningsSummary:
        """Return a summary of unacknowledged warning counts.

        Returns:
            Summary with the unacknowledged warning count.
        """
        return PipelineWarningsSummary(unacknowledged_count=self.db.count_unacknowledged())

    def acknowledge(self, warning_id: str) -> PipelineWarning | None:
        """Acknowledge a single warning by id.

        Args:
            warning_id: Identifier of the warning to acknowledge.

        Returns:
            Updated warning, or None if not found.
        """
        return self.db.acknowledge(warning_id)

    def acknowledge_all(self) -> int:
        """Acknowledge every unacknowledged warning.

        Returns:
            Number of warnings acknowledged.
        """
        return self.db.acknowledge_all()


def _truncate_message(message: str) -> str:
    """Normalize whitespace and truncate a warning message to the max length.

    Args:
        message: Raw warning message text.

    Returns:
        Cleaned message, truncated with an ellipsis when over the limit.
    """
    text = " ".join(message.strip().split())
    if not text:
        return "Pipeline warning"
    if len(text) <= MAX_WARNING_MESSAGE_LENGTH:
        return text
    return text[: MAX_WARNING_MESSAGE_LENGTH - 1].rstrip() + "…"
