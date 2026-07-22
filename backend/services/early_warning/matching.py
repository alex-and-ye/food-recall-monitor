from __future__ import annotations

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
    EXACT_URL = "exact_url"
    CONTENT_HASH = "content_hash"
    TITLE = "title"
    ENTITY_DATE = "entity_date"
    SEMANTIC = "semantic"


@dataclass(frozen=True)
class MatchResult:
    matched_id: str
    kind: MatchKind
    score: float = 1.0
    entity_overlap: tuple[str, ...] = ()
    requires_review: bool = False


SemanticScorer = Callable[[EarlyWarningIncident, EarlyWarningIncident], float | None]


def canonicalize_url(url: str) -> str:
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
    normalized = normalize_text(title)
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(character for character in normalized if not unicodedata.combining(character))
    return " ".join(re.findall(r"\w+", ascii_text.casefold()))


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
    overlaps: list[str] = []
    for field_name in ("product_name", "company_name", "hazard_type", "country"):
        left_value = normalize_text(str(getattr(left, field_name)))
        right_value = normalize_text(str(getattr(right, field_name)))
        if left_value and left_value == right_value:
            overlaps.append(field_name)
    return tuple(overlaps)


def _entity_date_match(
    left: EarlyWarningIncident,
    right: EarlyWarningIncident,
    *,
    overlap: tuple[str, ...],
    date_window_days: int,
) -> bool:
    has_primary_entity = "product_name" in overlap or "company_name" in overlap
    return (
        has_primary_entity
        and len(overlap) >= 2
        and _dates_within(left.publication_date, right.publication_date, date_window_days)
    )


def _dates_within(left: date | None, right: date | None, window_days: int) -> bool:
    if left is None or right is None:
        return False
    return abs((left - right).days) <= window_days


def _has_exact_url(left: EarlyWarningIncident, right: EarlyWarningIncident) -> bool:
    return bool(_incident_urls(left).intersection(_incident_urls(right)))


def _has_exact_content_hash(left: EarlyWarningIncident, right: EarlyWarningIncident) -> bool:
    left_hashes = _content_hashes(left.evidence)
    return bool(left_hashes.intersection(_content_hashes(right.evidence)))


def _has_exact_title(left: EarlyWarningIncident, right: EarlyWarningIncident) -> bool:
    left_titles = _title_fingerprints(left.evidence)
    return bool(left_titles.intersection(_title_fingerprints(right.evidence)))


def _incident_urls(incident: EarlyWarningIncident) -> set[str]:
    urls = {incident.primary_source_url}
    for evidence in incident.evidence:
        urls.add(evidence.url)
        urls.update(evidence.redirected_url_aliases)
    return {canonicalize_url(url) for url in urls if canonicalize_url(url)}


def _content_hashes(evidence: Iterable[IncidentEvidence]) -> set[str]:
    return {
        item.content_hash.strip().lower()
        for item in evidence
        if item.content_hash.strip()
    }


def _title_fingerprints(evidence: Iterable[IncidentEvidence]) -> set[str]:
    return {
        fingerprint
        for item in evidence
        if (fingerprint := normalized_title_fingerprint(item.title))
    }
