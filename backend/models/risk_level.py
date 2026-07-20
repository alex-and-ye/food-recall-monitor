from enum import StrEnum

class RiskLevel(StrEnum):
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

RISK_LEVELS: frozenset[str] = frozenset(RiskLevel)
