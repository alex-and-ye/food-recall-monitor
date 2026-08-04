"""Abstract persistence contract for pipeline warning records.

Defines the repository interface for creating, listing, acknowledging,
and deleting operational warnings raised during pipeline runs.
"""

from abc import ABC, abstractmethod

from models.pipeline_warning import PipelineWarning, PipelineWarningCreate

class PipelineWarningsDBInterface(ABC):
    """Repository interface for pipeline warning persistence."""

    @abstractmethod
    def create(self, warning: PipelineWarningCreate) -> PipelineWarning:
        """Create and persist a new pipeline warning.

        Args:
            warning: Warning creation payload (category, message, etc.).

        Returns:
            The stored warning with generated ID and timestamp.
        """
        pass

    @abstractmethod
    def list_warnings(self, *, acknowledged: bool | None = None) -> list[PipelineWarning]:
        """List warnings, optionally filtered by acknowledgment status.

        Args:
            acknowledged: If set, only warnings with this acknowledgment flag.

        Returns:
            Matching warnings, typically newest first.
        """
        pass

    @abstractmethod
    def get_warning(self, warning_id: str) -> PipelineWarning | None:
        """Fetch a warning by identifier.

        Args:
            warning_id: Unique warning ID.

        Returns:
            The matching warning, or None if not found.
        """
        pass

    @abstractmethod
    def acknowledge(self, warning_id: str) -> PipelineWarning | None:
        """Mark a single warning as acknowledged.

        Args:
            warning_id: Unique warning ID.

        Returns:
            The updated warning, or None if not found.
        """
        pass

    @abstractmethod
    def acknowledge_all(self) -> int:
        """Mark all unacknowledged warnings as acknowledged.

        Returns:
            Number of warnings that were updated.
        """
        pass

    @abstractmethod
    def count_unacknowledged(self) -> int:
        """Count warnings that have not been acknowledged.

        Returns:
            Number of unacknowledged warnings.
        """
        pass

    @abstractmethod
    def delete(self, warning_id: str) -> bool:
        """Delete a warning by identifier.

        Args:
            warning_id: Unique warning ID.

        Returns:
            True if a record was deleted; False if not found.
        """
        pass
