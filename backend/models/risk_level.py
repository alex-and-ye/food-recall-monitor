"""Risk level enumeration and related choice constants.

Used by the official pipeline for structured alert risk classification
and prompt/display ordering.
"""

from enum import StrEnum

class RiskLevel(StrEnum):
    """Qualitative risk level assigned to a food recall alert."""

    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    UNKNOWN = "Unknown"

# Prompt / display order (not alphabetical).
RISK_LEVEL_CHOICES: tuple[RiskLevel, ...] = (
    RiskLevel.LOW,
    RiskLevel.MEDIUM,
    RiskLevel.HIGH,
    RiskLevel.UNKNOWN,
)

# All valid risk-level string values.
RISK_LEVELS: frozenset[str] = frozenset(RiskLevel)
