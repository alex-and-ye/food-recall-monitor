"""Alert list sort-order options.

Defines allowed sort directions for dashboard and API listing endpoints.
"""

from enum import StrEnum

class SortBy(StrEnum):
    """Sort direction for alert or incident listings by date."""

    LATEST = "latest"
    OLDEST = "oldest"

# All valid sort-option string values.
VALID_SORT_OPTIONS: frozenset[str] = frozenset(SortBy)
