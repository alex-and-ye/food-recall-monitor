"""Confidence scoring rules for early-warning food-safety incidents.

Combines source-kind base weights with corroboration, evidence quality, and
staleness modifiers into a bounded score with an audit trail of applied rules.
"""

from dataclasses import dataclass, field
from typing import Mapping

from models.early_warning_incident import (
    EarlyWarningIncidentCreate,
    SourceKind,
    VerificationStatus,
)

# Base confidence points by publisher/source classification.
SOURCE_KIND_BASE_WEIGHTS: dict[SourceKind, int] = {
    SourceKind.OFFICIAL_RECALL: 100,
    SourceKind.GOVERNMENT_INVESTIGATION: 95,
    SourceKind.WHO_FAO: 90,
    SourceKind.COMPANY_RELEASE: 85,
    SourceKind.MAJOR_NEWS: 75,
    SourceKind.TRADE_PUBLICATION: 65,
    SourceKind.UNKNOWN: 40,
    SourceKind.BLOG: 20,
}


@dataclass(frozen=True)
class ConfidencePolicy:
    """Tunable modifiers and caps for confidence calculation.

    Attributes:
        base_weights: Mapping from source kind to base score points.
        corroboration_per_source: Points added per extra independent source.
        corroboration_cap: Maximum total corroboration bonus.
        explicit_product_modifier: Bonus when product evidence is present.
        explicit_hazard_modifier: Bonus when hazard evidence is present.
        explicit_date_modifier: Bonus when a publication date is present.
        trusted_domain_modifier: Bonus for trusted-domain overrides.
        stale_reporting_modifier: Penalty for stale reporting signals.
        vague_reporting_modifier: Penalty for vague reporting signals.
        unofficial_cap: Maximum score for non-official matches.
    """

    base_weights: Mapping[SourceKind | str, int] = field(
        default_factory=lambda: dict(SOURCE_KIND_BASE_WEIGHTS)
    )
    corroboration_per_source: int = 5
    corroboration_cap: int = 15
    explicit_product_modifier: int = 4
    explicit_hazard_modifier: int = 4
    explicit_date_modifier: int = 2
    trusted_domain_modifier: int = 5
    stale_reporting_modifier: int = -10
    vague_reporting_modifier: int = -10
    unofficial_cap: int = 99


@dataclass(frozen=True)
class ConfidenceScore:
    """Result of a confidence calculation with rule explanations.

    Attributes:
        score: Final bounded confidence score.
        reasons: Human-readable descriptions of each applied rule.
    """

    score: int
    reasons: tuple[str, ...]


def calculate_confidence(
    source_kind: SourceKind | str,
    *,
    independent_source_count: int = 1,
    has_product_evidence: bool = False,
    has_hazard_evidence: bool = False,
    has_date_evidence: bool = False,
    trusted_domain_override: bool = False,
    stale_reporting: bool = False,
    vague_reporting: bool = False,
    official_match: bool = False,
    policy: ConfidencePolicy | None = None,
) -> ConfidenceScore:
    """Calculate a bounded score and preserve every applied rule.

    Args:
        source_kind: Publisher/source classification.
        independent_source_count: Count of distinct corroborating sources.
        has_product_evidence: Whether an explicit product name is present.
        has_hazard_evidence: Whether an explicit hazard type is present.
        has_date_evidence: Whether a publication date is present.
        trusted_domain_override: Whether a trusted-domain bonus applies.
        stale_reporting: Whether stale-reporting penalty applies.
        vague_reporting: Whether vague-reporting penalty applies.
        official_match: When True, force score 100 for official confirmation.
        policy: Optional override for scoring weights and modifiers.

    Returns:
        ConfidenceScore with the final score and applied-rule reasons.
    """
    rules = policy or ConfidencePolicy()
    source_kind = SourceKind(source_kind)
    if official_match:
        return ConfidenceScore(
            score=100,
            reasons=("official recall match: score set to 100",),
        )

    base = _base_weight(source_kind, rules.base_weights)
    score = base
    reasons = [f"source kind {source_kind.value}: base {base}"]

    corroborating_sources = max(0, independent_source_count - 1)
    if corroborating_sources:
        modifier = min(
            corroborating_sources * rules.corroboration_per_source,
            rules.corroboration_cap,
        )
        score += modifier
        reasons.append(
            f"{corroborating_sources} independent corroborating source(s): +{modifier}"
        )

    modifiers = (
        (
            has_product_evidence,
            rules.explicit_product_modifier,
            "explicit product evidence",
        ),
        (
            has_hazard_evidence,
            rules.explicit_hazard_modifier,
            "explicit hazard evidence",
        ),
        (
            has_date_evidence,
            rules.explicit_date_modifier,
            "explicit date evidence",
        ),
        (
            trusted_domain_override,
            rules.trusted_domain_modifier,
            "trusted-domain override",
        ),
        (stale_reporting, rules.stale_reporting_modifier, "stale reporting"),
        (vague_reporting, rules.vague_reporting_modifier, "vague reporting"),
    )
    for applies, modifier, label in modifiers:
        if not applies or modifier == 0:
            continue
        score += modifier
        reasons.append(f"{label}: {modifier:+d}")

    bounded = min(rules.unofficial_cap, max(0, score))
    if bounded != score:
        reasons.append(f"unofficial confidence bounded to {bounded}")
    return ConfidenceScore(score=bounded, reasons=tuple(reasons))


def _base_weight(
    source_kind: SourceKind,
    weights: Mapping[SourceKind | str, int],
) -> int:
    """Resolve the base score for a source kind from a weight mapping.

    Args:
        source_kind: Source classification enum value.
        weights: Mapping of SourceKind or string keys to base points.

    Returns:
        Integer base weight, falling back to UNKNOWN when missing.
    """
    value = weights.get(source_kind)
    if value is None:
        value = weights.get(source_kind.value)
    if value is None:
        value = weights.get(SourceKind.UNKNOWN)
    if value is None:
        value = weights.get(SourceKind.UNKNOWN.value, SOURCE_KIND_BASE_WEIGHTS[SourceKind.UNKNOWN])
    return int(value)


def calculate_incident_confidence(
    incident: EarlyWarningIncidentCreate,
    *,
    independent_source_count: int | None = None,
    trusted_domain_override: bool = False,
    stale_reporting: bool = False,
    vague_reporting: bool = False,
    policy: ConfidencePolicy | None = None,
) -> ConfidenceScore:
    """Derive confidence for an incident from its fields and evidence.

    Args:
        incident: Incident create/update payload to score.
        independent_source_count: Optional override for corroboration count.
        trusted_domain_override: Whether a trusted-domain bonus applies.
        stale_reporting: Whether stale-reporting penalty applies.
        vague_reporting: Whether vague-reporting penalty applies.
        policy: Optional override for scoring weights and modifiers.

    Returns:
        ConfidenceScore derived from the incident contents.
    """
    domains = {
        evidence.domain.strip().lower()
        for evidence in incident.evidence
        if evidence.domain.strip()
    }
    if not domains:
        domains = {
            evidence.url.strip().lower()
            for evidence in incident.evidence
            if evidence.url.strip()
        }
    source_count = independent_source_count
    if source_count is None:
        source_count = max(1, len(domains))

    return calculate_confidence(
        incident.source_kind,
        independent_source_count=source_count,
        has_product_evidence=bool(incident.product_name),
        has_hazard_evidence=bool(incident.hazard_type),
        has_date_evidence=incident.publication_date is not None,
        trusted_domain_override=trusted_domain_override,
        stale_reporting=stale_reporting,
        vague_reporting=vague_reporting,
        official_match=(
            incident.verification_status == VerificationStatus.OFFICIALLY_CONFIRMED
            or bool(incident.linked_official_alert_ids)
        ),
        policy=policy,
    )
