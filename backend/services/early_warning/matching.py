"""Deduplication and matching helpers for early-warning incidents.

Provides URL canonicalization, entity-text matching, and ordered matchers
that cluster incidents and link them to official food-recall alerts.
"""

import hashlib
import re
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from models.early_warning_incident import EarlyWarningIncident, IncidentEvidence
from models.food_recall_alert import FoodRecallAlert

# Query keys stripped during URL canonicalization (tracking/analytics params).
TRACKING_QUERY_KEYS = frozenset(
    {
        "fbclid",
        "gclid",
        "mc_cid",
        "mc_eid",
        "ref",
        "source",
        "utm_campaign",
        "utm_content",
        "utm_medium",
        "utm_source",
        "utm_term",
    }
)


class MatchKind(StrEnum):
    """Classification of how two records were matched."""

    EXACT_URL = "exact_url"
    CONTENT_HASH = "content_hash"
    TITLE = "title"
    ENTITY_DATE = "entity_date"
    SEMANTIC = "semantic"


@dataclass(frozen=True)
class MatchResult:
    """Outcome of matching an incoming incident against a candidate.

    Attributes:
        matched_id: Identifier of the matched incident or official alert.
        kind: Match strategy that produced the result.
        score: Similarity score (1.0 for exact matchers).
        entity_overlap: Entity field names that overlapped.
        requires_review: True when a semantic match is below auto-merge threshold.
    """

    matched_id: str
    kind: MatchKind
    score: float = 1.0
    entity_overlap: tuple[str, ...] = ()
    requires_review: bool = False


SemanticScorer = Callable[[EarlyWarningIncident, EarlyWarningIncident], float | None]  # Optional semantic similarity fn.


def canonicalize_url(url: str) -> str:
    """Normalize a URL for equality comparison.

    Lowercases scheme/host, drops default ports, collapses paths, strips
    tracking query parameters, and removes fragments.

    Args:
        url: Raw URL string.

    Returns:
        Canonical URL, or the stripped original when scheme/host are missing.
    """
    text = url.strip()
    if not text:
        return ""
    parsed = urlsplit(text)
    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower()
    if not scheme or not hostname:
        return text

    port = parsed.port
    if port and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    ):
        netloc = f"{hostname}:{port}"
    else:
        netloc = hostname

    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")
    query = urlencode(
        sorted(
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if key.lower() not in TRACKING_QUERY_KEYS
        )
    )
    return urlunsplit((scheme, netloc, path, query, ""))


def normalized_title_fingerprint(title: str) -> str:
    """Hash a normalized title for exact-title matching.

    Args:
        title: Evidence title text.

    Returns:
        SHA-256 hex digest of the normalized title, or empty string.
    """
    normalized = normalize_text(title)
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def normalize_text(value: str) -> str:
    """Normalize text for fuzzy entity comparison.

    Applies NFKD, strips diacritics, expands ``&`` to ``and``, lowercases,
    and keeps alphanumeric word tokens only.

    Args:
        value: Raw entity or title string.

    Returns:
        Space-joined normalized tokens.
    """
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(character for character in normalized if not unicodedata.combining(character))
    # Treat "&" as "and" so "Waitrose & Partners" matches "Waitrose and Partners".
    ascii_text = ascii_text.replace("&", " and ")
    return " ".join(re.findall(r"\w+", ascii_text.casefold()))


def entity_text_match(left: str, right: str, *, min_tokens: int = 2) -> bool:
    """Match entity strings exactly or when one token-set contains the other.

    Args:
        left: First entity string.
        right: Second entity string.
        min_tokens: Minimum token count required for subset containment.

    Returns:
        True when the entities are considered the same.
    """
    left_norm = normalize_text(left)
    right_norm = normalize_text(right)
    if not left_norm or not right_norm:
        return False
    if left_norm == right_norm:
        return True
    left_tokens = set(left_norm.split())
    right_tokens = set(right_norm.split())
    shorter, longer = (
        (left_tokens, right_tokens)
        if len(left_tokens) <= len(right_tokens)
        else (right_tokens, left_tokens)
    )
    # Require enough shared specificity to avoid collapsing on a single token,
    # unless the caller lowers min_tokens (e.g. company after a product match).
    return len(shorter) >= min_tokens and shorter <= longer


class IncidentMatcher:
    """Matches incidents in increasing-cost order."""

    def __init__(
        self,
        *,
        date_window_days: int = 7,
        semantic_scorer: SemanticScorer | None = None,
        semantic_auto_threshold: float = 0.92,
        semantic_review_threshold: float = 0.82,
    ) -> None:
        """Configure match windows and optional semantic scoring.

        Args:
            date_window_days: Max day gap for entity-date matches.
            semantic_scorer: Optional callable returning a similarity score.
            semantic_auto_threshold: Score at/above which auto-merge is allowed.
            semantic_review_threshold: Minimum score for a review-flagged match.

        Raises:
            ValueError: If date window or semantic thresholds are invalid.
        """
        if date_window_days < 0:
            raise ValueError("date_window_days must be non-negative")
        if not 0.0 <= semantic_review_threshold <= semantic_auto_threshold <= 1.0:
            raise ValueError("semantic thresholds must satisfy 0 <= review <= auto <= 1")
        self.date_window_days = date_window_days
        self.semantic_scorer = semantic_scorer
        self.semantic_auto_threshold = semantic_auto_threshold
        self.semantic_review_threshold = semantic_review_threshold

    def find_match(
        self,
        incoming: EarlyWarningIncident,
        candidates: Iterable[EarlyWarningIncident],
    ) -> MatchResult | None:
        """Find the best match for ``incoming`` among ``candidates``.

        Tries exact URL/hash/title, then entity-date, then semantic scoring.

        Args:
            incoming: New or updated incident to match.
            candidates: Existing incidents to compare against.

        Returns:
            Best MatchResult, or None when no match is found.
        """
        candidate_list = sorted(candidates, key=lambda item: item.incident_id)
        exact_matchers = (
            (MatchKind.EXACT_URL, _has_exact_url),
            (MatchKind.CONTENT_HASH, _has_exact_content_hash),
            (MatchKind.TITLE, _has_exact_title),
        )
        for kind, predicate in exact_matchers:
            for candidate in candidate_list:
                if candidate.incident_id == incoming.incident_id:
                    continue
                if predicate(incoming, candidate):
                    return MatchResult(matched_id=candidate.incident_id, kind=kind)

        for candidate in candidate_list:
            if candidate.incident_id == incoming.incident_id:
                continue
            overlap = entity_overlap(incoming, candidate)
            if _entity_date_match(
                incoming,
                candidate,
                overlap=overlap,
                date_window_days=self.date_window_days,
            ):
                return MatchResult(
                    matched_id=candidate.incident_id,
                    kind=MatchKind.ENTITY_DATE,
                    entity_overlap=overlap,
                )

        if self.semantic_scorer is None:
            return None
        semantic_matches: list[MatchResult] = []
        for candidate in candidate_list:
            if candidate.incident_id == incoming.incident_id:
                continue
            overlap = entity_overlap(incoming, candidate)
            # Similar wording alone is never enough to cluster two incidents.
            if not overlap:
                continue
            score = self.semantic_scorer(incoming, candidate)
            if score is None or score < self.semantic_review_threshold:
                continue
            semantic_matches.append(
                MatchResult(
                    matched_id=candidate.incident_id,
                    kind=MatchKind.SEMANTIC,
                    score=float(score),
                    entity_overlap=overlap,
                    requires_review=score < self.semantic_auto_threshold,
                )
            )
        if not semantic_matches:
            return None
        return sorted(
            semantic_matches,
            key=lambda result: (-result.score, result.matched_id),
        )[0]


def find_incident_match(
    incoming: EarlyWarningIncident,
    candidates: Iterable[EarlyWarningIncident],
    *,
    date_window_days: int = 7,
    semantic_scorer: SemanticScorer | None = None,
) -> MatchResult | None:
    """Convenience wrapper around IncidentMatcher.find_match.

    Args:
        incoming: Incident to match.
        candidates: Existing incidents.
        date_window_days: Entity-date window in days.
        semantic_scorer: Optional semantic scorer.

    Returns:
        MatchResult or None.
    """
    return IncidentMatcher(
        date_window_days=date_window_days,
        semantic_scorer=semantic_scorer,
    ).find_match(incoming, candidates)


def find_official_match(
    incident: EarlyWarningIncident,
    alerts: Iterable[FoodRecallAlert],
    *,
    date_window_days: int = 7,
) -> tuple[FoodRecallAlert, MatchResult] | None:
    """Match an early-warning incident against official recall alerts.

    Args:
        incident: Early-warning incident to verify.
        alerts: Official food-recall alerts.
        date_window_days: Max day gap for entity-date matches.

    Returns:
        Tuple of (alert, MatchResult) on success, otherwise None.
    """
    ordered = sorted(alerts, key=lambda alert: alert.alert_id)
    incident_urls = _incident_urls(incident)
    for alert in ordered:
        if canonicalize_url(alert.source_url) in incident_urls:
            return alert, MatchResult(alert.alert_id, MatchKind.EXACT_URL)

    for alert in ordered:
        if not _dates_within(incident.publication_date, alert.recall_date, date_window_days):
            continue
        if normalize_text(incident.product_name) != normalize_text(alert.product_name):
            continue
        if (
            incident.hazard_type
            and alert.hazard_type
            and normalize_text(incident.hazard_type) != normalize_text(alert.hazard_type)
        ):
            continue
        overlap = ["product_name", "publication_date"]
        if incident.hazard_type and alert.hazard_type:
            overlap.append("hazard_type")
        return alert, MatchResult(
            matched_id=alert.alert_id,
            kind=MatchKind.ENTITY_DATE,
            entity_overlap=tuple(overlap),
        )
    return None


def entity_overlap(
    left: EarlyWarningIncident,
    right: EarlyWarningIncident,
) -> tuple[str, ...]:
    """Return overlapping entity field names between two incidents.

    Args:
        left: First incident.
        right: Second incident.

    Returns:
        Tuple of overlapping field names (product, company, and/or hazard).
    """
    overlaps: list[str] = []
    # Country labels are too inconsistent across sources ("UK" vs "United Kingdom")
    # to use as a hard identity signal; matching is based on product/company/hazard.
    if entity_text_match(left.product_name, right.product_name):
        overlaps.append("product_name")
    # After a product match, allow a shorter company label ("Waitrose") to align
    # with a fuller legal name ("Waitrose & Partners").
    company_min_tokens = 1 if "product_name" in overlaps else 2
    if entity_text_match(
        left.company_name,
        right.company_name,
        min_tokens=company_min_tokens,
    ):
        overlaps.append("company_name")
    if entity_text_match(left.hazard_type, right.hazard_type):
        overlaps.append("hazard_type")
    return tuple(overlaps)


def _entity_date_match(
    left: EarlyWarningIncident,
    right: EarlyWarningIncident,
    *,
    overlap: tuple[str, ...],
    date_window_days: int,
) -> bool:
    """Return whether entity overlap plus dates justify a cluster merge.

    Args:
        left: First incident.
        right: Second incident.
        overlap: Precomputed entity overlap fields.
        date_window_days: Allowed publication-date gap.

    Returns:
        True when the pair should merge via entity-date matching.
    """
    has_primary_entity = "product_name" in overlap or "company_name" in overlap
    if not (has_primary_entity and len(overlap) >= 2):
        return False
    if left.publication_date is None or right.publication_date is None:
        # Missing dates should not create near-duplicate incidents when product and
        # company already align across sources.
        return "product_name" in overlap and "company_name" in overlap
    return _dates_within(left.publication_date, right.publication_date, date_window_days)


def _dates_within(left: date | None, right: date | None, window_days: int) -> bool:
    """Return whether two dates fall within ``window_days`` of each other.

    Args:
        left: First date (may be None).
        right: Second date (may be None).
        window_days: Inclusive maximum absolute day difference.

    Returns:
        True when both dates exist and are within the window.
    """
    if left is None or right is None:
        return False
    return abs((left - right).days) <= window_days


def _has_exact_url(left: EarlyWarningIncident, right: EarlyWarningIncident) -> bool:
    """Return whether two incidents share a canonical URL.

    Args:
        left: First incident.
        right: Second incident.

    Returns:
        True when URL sets intersect.
    """
    return bool(_incident_urls(left).intersection(_incident_urls(right)))


def _has_exact_content_hash(left: EarlyWarningIncident, right: EarlyWarningIncident) -> bool:
    """Return whether two incidents share a content hash.

    Args:
        left: First incident.
        right: Second incident.

    Returns:
        True when content-hash sets intersect.
    """
    left_hashes = _content_hashes(left.evidence)
    return bool(left_hashes.intersection(_content_hashes(right.evidence)))


def _has_exact_title(left: EarlyWarningIncident, right: EarlyWarningIncident) -> bool:
    """Return whether two incidents share a normalized title fingerprint.

    Args:
        left: First incident.
        right: Second incident.

    Returns:
        True when title fingerprint sets intersect.
    """
    left_titles = _title_fingerprints(left.evidence)
    return bool(left_titles.intersection(_title_fingerprints(right.evidence)))


def _incident_urls(incident: EarlyWarningIncident) -> set[str]:
    """Collect canonical URLs from an incident and its evidence.

    Args:
        incident: Incident whose URLs are collected.

    Returns:
        Set of non-empty canonical URL strings.
    """
    urls = {incident.primary_source_url}
    for evidence in incident.evidence:
        urls.add(evidence.url)
        urls.update(evidence.redirected_url_aliases)
    return {canonicalize_url(url) for url in urls if canonicalize_url(url)}


def _content_hashes(evidence: Iterable[IncidentEvidence]) -> set[str]:
    """Collect non-empty lowercased content hashes from evidence.

    Args:
        evidence: Evidence items to scan.

    Returns:
        Set of content hash strings.
    """
    return {
        item.content_hash.strip().lower()
        for item in evidence
        if item.content_hash.strip()
    }


def _title_fingerprints(evidence: Iterable[IncidentEvidence]) -> set[str]:
    """Collect non-empty title fingerprints from evidence.

    Args:
        evidence: Evidence items to scan.

    Returns:
        Set of title fingerprint digests.
    """
    return {
        fingerprint
        for item in evidence
        if (fingerprint := normalized_title_fingerprint(item.title))
    }
