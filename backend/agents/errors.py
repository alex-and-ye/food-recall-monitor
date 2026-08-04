"""Custom exceptions for agent pipeline source fetching failures."""


class SourceFetchError(Exception):
    """Raised when all requested recall sources fail to fetch."""

    def __init__(self, failures: dict[str, str]) -> None:
        """Initialize with a mapping of source names to error messages.

        Args:
            failures: Source name keyed to the fetch error description for that source.
        """
        self.failures = failures
        super().__init__(_format_failures(failures))


def _format_failures(failures: dict[str, str]) -> str:
    """Format source failure details into a single human-readable message."""
    details = "; ".join(f"{source}: {error}" for source, error in failures.items())
    return f"Failed to fetch requested source(s): {details}"
