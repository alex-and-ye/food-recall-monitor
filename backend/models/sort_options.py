from enum import StrEnum

class SortBy(StrEnum):
    LATEST = "latest"
    OLDEST = "oldest"

VALID_SORT_OPTIONS: frozenset[str] = frozenset(SortBy)
