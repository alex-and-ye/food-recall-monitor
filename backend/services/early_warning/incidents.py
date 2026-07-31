import hashlib
import uuid
from collections import Counter
from datetime import date, datetime, timezone
from typing import Protocol

from db.early_warning_interface import EarlyWarningIncidentsDBInterface
from models.early_warning_incident import (
    EarlyWarningIncident,
    EarlyWarningIncidentCreate,
    IncidentsVersion,
    IncidentStatusCounts,
    IncidentType,
    IncidentEvidence,
    SourceKind,
    VerificationStatus,
)
from services.early_warning.confidence import (
    ConfidencePolicy,
    SOURCE_KIND_BASE_WEIGHTS,
    calculate_incident_confidence,
)
from services.early_warning.matching import (
    IncidentMatcher,
    canonicalize_url,
    entity_overlap,
    normalize_text,
)

INCIDENT_ID_NAMESPACE = uuid.UUID("257e537e-d840-531f-aec4-5ca8f741fd37")

class IncidentSemanticIndex(Protocol):
    def query_incidents(
        self,
        incident: EarlyWarningIncident,
        *,
        limit: int = 10,
    ) -> list[object]: ...

    def upsert_incident(self, incident: EarlyWarningIncident) -> None: ...

class EarlyWarningIncidentService:
    def __init__(
        self,
        store: EarlyWarningIncidentsDBInterface,
        *,
        matcher: IncidentMatcher | None = None,
        confidence_policy: ConfidencePolicy | None = None,
        semantic_index: IncidentSemanticIndex | None = None,
        semantic_review_threshold: float = 0.82,
        semantic_auto_merge_threshold: float = 0.92,
        semantic_result_limit: int = 10,
    ) -> None:
        self.store = store
        self.matcher = matcher or IncidentMatcher()
        self.confidence_policy = confidence_policy
        self.semantic_index = semantic_index
        self.semantic_review_threshold = semantic_review_threshold
        self.semantic_auto_merge_threshold = semantic_auto_merge_threshold
        self.semantic_result_limit = semantic_result_limit

    def save_incident(
        self,
        incident: EarlyWarningIncidentCreate | EarlyWarningIncident,
    ) -> EarlyWarningIncident:
        prepared = self._prepare(incident)
        existing_same_id = self.store.get_incident(prepared.incident_id)
        if existing_same_id is not None:
            return self._persist(self._merge(existing_same_id, prepared))

        match = self.matcher.find_match(prepared, self.store.list_incidents())
        if match is not None and not match.requires_review:
            existing = self.store.get_incident(match.matched_id)
            if existing is not None:
                return self._persist(self._merge(existing, prepared))
        prepared, semantic_target_id = self._apply_semantic_match(prepared)
        if semantic_target_id is not None:
            existing = self.store.get_incident(semantic_target_id)
            if existing is not None:
                return self._persist(self._merge(existing, prepared))
        return self._persist(prepared)

    create_or_update = save_incident

    def get_incident(self, incident_id: str) -> EarlyWarningIncident | None:
        return self.store.get_incident(incident_id)

    def list_incidents(
        self,
        *,
        search: str | None = None,
        verification_status: VerificationStatus | None = None,
        incident_type: IncidentType | None = None,
        minimum_confidence: int | None = None,
        country: str | None = None,
        source_kind: SourceKind | None = None,
        publication_date: date | None = None,
        sort_by: str | None = None,
    ) -> list[EarlyWarningIncident]:
        incidents = self.store.list_incidents(
            verification_status=verification_status,
            incident_type=incident_type,
            minimum_confidence=minimum_confidence,
            country=country,
            source_kind=source_kind,
        )
        if publication_date is not None:
            incidents = [
                incident
                for incident in incidents
                if incident.effective_publication_date() == publication_date
            ]
        query = (search or "").strip().casefold()
        if query:
            incidents = [
                incident
                for incident in incidents
                if query
                in " ".join(
                    (
                        incident.product_name,
                        incident.company_name,
                        incident.product_category,
                        incident.hazard_type,
                        incident.incident_reason,
                        incident.summary,
                        incident.country,
                        incident.primary_publisher,
                    )
                ).casefold()
            ]
        return _sort_incidents(incidents, sort_by=sort_by)

    def get_status_counts(self) -> IncidentStatusCounts:
        counts = Counter(incident.verification_status.value for incident in self.store.list_incidents())
        return IncidentStatusCounts(**counts)

    def get_version(self) -> IncidentsVersion:
        incidents = self.store.list_incidents()
        version_material = "\0".join(
            f"{incident.incident_id}:{incident.last_discovered_at.isoformat()}:"
            f"{incident.verification_status.value}:{incident.confidence_score}"
            for incident in sorted(incidents, key=lambda item: item.incident_id)
        )
        return IncidentsVersion(
            count=len(incidents),
            fingerprint=hashlib.sha256(version_material.encode("utf-8")).hexdigest(),
        )

    def _prepare(
        self,
        value: EarlyWarningIncidentCreate | EarlyWarningIncident,
    ) -> EarlyWarningIncident:
        payload = value.model_dump(exclude={"incident_id"})
        evidence = _ensure_primary_evidence(
            list(value.evidence),
            primary_url=value.primary_source_url,
            source_kind=value.source_kind,
            publication_date=value.publication_date,
            publisher=value.primary_publisher,
            domain=value.primary_source_domain,
        )
        fingerprint = value.cluster_fingerprint or build_cluster_fingerprint(value)
        incident_id = (
            value.incident_id
            if isinstance(value, EarlyWarningIncident)
            else build_incident_id(fingerprint)
        )
        payload.update(
            {
                "incident_id": incident_id,
                "cluster_fingerprint": fingerprint,
                "evidence": evidence,
            }
        )
        prepared = EarlyWarningIncident.model_validate(payload)
        return _with_derived_confidence(prepared, policy=self.confidence_policy)

    def _merge(
        self,
        existing: EarlyWarningIncident,
        incoming: EarlyWarningIncident,
    ) -> EarlyWarningIncident:
        evidence = _merge_evidence(existing.evidence, incoming.evidence)
        source_kind = _highest_weight_source_kind(
            [existing.source_kind, incoming.source_kind]
            + [item.source_kind for item in evidence]
        )
        terminal_statuses = {
            VerificationStatus.DISMISSED,
            VerificationStatus.SUPERSEDED,
            VerificationStatus.OFFICIALLY_CONFIRMED,
        }
        if existing.verification_status in terminal_statuses:
            status = existing.verification_status
        elif incoming.verification_status in terminal_statuses:
            status = incoming.verification_status
        elif _independent_source_count(evidence) > 1:
            status = VerificationStatus.CORROBORATED
        elif existing.verification_status == VerificationStatus.CORROBORATED:
            status = VerificationStatus.CORROBORATED
        else:
            status = VerificationStatus.PENDING

        update = incoming.model_dump(exclude={"incident_id"})
        for field_name in (
            "product_name",
            "company_name",
            "product_category",
            "hazard_type",
            "incident_reason",
            "summary",
            "consumer_guidance",
            "country",
            "primary_source_domain",
            "primary_publisher",
            "original_language",
            "analyst_notes",
        ):
            if not update[field_name]:
                update[field_name] = getattr(existing, field_name)
        update["country"] = _preferred_country(existing.country, update.get("country") or "")
        for field_name in ("product_name", "company_name", "hazard_type"):
            update[field_name] = _preferred_entity_label(
                getattr(existing, field_name),
                update.get(field_name) or "",
            )
        update.update(
            {
                "incident_id": existing.incident_id,
                "cluster_fingerprint": existing.cluster_fingerprint,
                "first_discovered_at": min(
                    existing.first_discovered_at,
                    incoming.first_discovered_at,
                ),
                "last_discovered_at": max(
                    existing.last_discovered_at,
                    incoming.last_discovered_at,
                ),
                "publication_date": incoming.publication_date
                or existing.publication_date,
                "verification_status": status,
                "status_updated_at": (
                    datetime.now(timezone.utc)
                    if status != existing.verification_status
                    else existing.status_updated_at
                ),
                "source_kind": source_kind,
                "evidence": evidence,
                "affected_regions": _ordered_union(
                    existing.affected_regions,
                    incoming.affected_regions,
                ),
                "linked_official_alert_ids": _ordered_union(
                    existing.linked_official_alert_ids,
                    incoming.linked_official_alert_ids,
                ),
                "processing_errors": _ordered_union(
                    existing.processing_errors,
                    incoming.processing_errors,
                ),
                "extraction_completeness": max(
                    existing.extraction_completeness,
                    incoming.extraction_completeness,
                ),
            }
        )
        merged = EarlyWarningIncident.model_validate(update)
        return _with_derived_confidence(merged, policy=self.confidence_policy)

    def _persist(self, incident: EarlyWarningIncident) -> EarlyWarningIncident:
        stored = self.store.upsert_incident(incident)
        if self.semantic_index is not None:
            try:
                self.semantic_index.upsert_incident(stored)
            except Exception:
                # The semantic collection is a derived, rebuildable index.
                # Primary incident persistence must not depend on embedding.
                pass
        return stored

    def _apply_semantic_match(
        self,
        incident: EarlyWarningIncident,
    ) -> tuple[EarlyWarningIncident, str | None]:
        if self.semantic_index is None:
            return incident, None
        try:
            neighbors = self.semantic_index.query_incidents(
                incident,
                limit=self.semantic_result_limit,
            )
        except Exception:
            return incident, None
        for neighbor in neighbors:
            record_id = str(getattr(neighbor, "record_id", "")).strip()
            score = float(getattr(neighbor, "score", 0.0))
            if not record_id or score < self.semantic_review_threshold:
                continue
            existing = self.store.get_incident(record_id)
            if existing is None:
                continue
            overlap = entity_overlap(incident, existing)
            if not {"product_name", "company_name"}.intersection(overlap):
                continue
            if score >= self.semantic_auto_merge_threshold:
                return incident, record_id
            return (
                incident.model_copy(
                    update={
                        "processing_errors": [
                            *incident.processing_errors,
                            f"possible_duplicate:{record_id}:{score:.3f}",
                        ]
                    }
                ),
                None,
            )
        return incident, None


IncidentsService = EarlyWarningIncidentService

def build_cluster_fingerprint(
    incident: EarlyWarningIncidentCreate | EarlyWarningIncident,
) -> str:
    # Omit country: extractors freely emit aliases ("UK" vs "United Kingdom") that
    # must not mint separate incident identities for the same recall.
    entity_parts = [
        normalize_text(incident.product_name),
        normalize_text(incident.company_name),
        normalize_text(incident.hazard_type),
        incident.publication_date.isoformat() if incident.publication_date else "",
    ]
    populated_entities = sum(bool(part) for part in entity_parts[:3])
    if populated_entities < 2:
        entity_parts.append(canonicalize_url(incident.primary_source_url))
    raw = "\0".join(entity_parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def build_incident_id(cluster_fingerprint: str) -> str:
    return str(uuid.uuid5(INCIDENT_ID_NAMESPACE, cluster_fingerprint))

def _preferred_country(*candidates: str) -> str:
    """Prefer the more descriptive non-empty country label without alias maps."""
    best = ""
    for candidate in candidates:
        text = str(candidate or "").strip()
        if len(text) > len(best):
            best = text
    return best

def _preferred_entity_label(*candidates: str) -> str:
    """Prefer the more specific non-empty entity label (more tokens / longer text)."""
    best = ""
    best_tokens = 0
    for candidate in candidates:
        text = str(candidate or "").strip()
        token_count = len(normalize_text(text).split()) if text else 0
        if token_count > best_tokens or (
            token_count == best_tokens and len(text) > len(best)
        ):
            best = text
            best_tokens = token_count
    return best

def _with_derived_confidence(
    incident: EarlyWarningIncident,
    *,
    policy: ConfidencePolicy | None,
) -> EarlyWarningIncident:
    result = calculate_incident_confidence(
        incident,
        independent_source_count=_independent_source_count(incident.evidence),
        policy=policy,
    )
    return incident.model_copy(
        update={
            "confidence_score": result.score,
            "confidence_reasons": list(result.reasons),
        }
    )

def _ensure_primary_evidence(
    evidence: list[IncidentEvidence],
    *,
    primary_url: str,
    source_kind: SourceKind,
    publication_date: object,
    publisher: str,
    domain: str,
) -> list[IncidentEvidence]:
    canonical_primary = canonicalize_url(primary_url)
    if not any(canonicalize_url(item.url) == canonical_primary for item in evidence):
        evidence.append(
            IncidentEvidence(
                url=primary_url,
                publication_date=publication_date,
                source_kind=source_kind,
                publisher=publisher,
                domain=domain,
            )
        )
    return _merge_evidence([], evidence)

def _merge_evidence(
    existing: list[IncidentEvidence],
    incoming: list[IncidentEvidence],
) -> list[IncidentEvidence]:
    by_url: dict[str, IncidentEvidence] = {}
    for item in [*existing, *incoming]:
        key = canonicalize_url(item.url) or item.url
        previous = by_url.get(key)
        if previous is None:
            by_url[key] = item.model_copy(deep=True)
            continue
        payload = item.model_dump()
        for field_name in ("title", "content_hash", "domain", "publisher"):
            if not payload[field_name]:
                payload[field_name] = getattr(previous, field_name)
        payload["publication_date"] = item.publication_date or previous.publication_date
        payload["redirected_url_aliases"] = _ordered_union(
            previous.redirected_url_aliases,
            item.redirected_url_aliases,
        )
        by_url[key] = IncidentEvidence.model_validate(payload)
    return [by_url[key] for key in sorted(by_url)]

def _independent_source_count(evidence: list[IncidentEvidence]) -> int:
    identities = {
        (item.domain.strip().casefold() or canonicalize_url(item.url))
        for item in evidence
        if item.domain.strip() or item.url.strip()
    }
    return max(1, len(identities))

def _highest_weight_source_kind(source_kinds: list[SourceKind]) -> SourceKind:
    return max(
        source_kinds or [SourceKind.UNKNOWN],
        key=lambda source_kind: (SOURCE_KIND_BASE_WEIGHTS[source_kind], source_kind.value),
    )

def _ordered_union(left: list[str], right: list[str]) -> list[str]:
    return list(dict.fromkeys([*left, *right]))

def _sort_incidents(
    incidents: list[EarlyWarningIncident],
    *,
    sort_by: str | None,
) -> list[EarlyWarningIncident]:
    """Sort like official recalls: publication date newest-first by default."""
    publication_key = lambda item: (
        item.effective_publication_date().isoformat(),
        item.incident_id,
    )
    if sort_by == "oldest":
        return sorted(incidents, key=publication_key)
    if sort_by == "confidence_high":
        return sorted(
            incidents,
            key=lambda item: (
                item.confidence_score,
                item.effective_publication_date().isoformat(),
                item.incident_id,
            ),
            reverse=True,
        )
    if sort_by == "confidence_low":
        return sorted(
            incidents,
            key=lambda item: (
                item.confidence_score,
                item.effective_publication_date().isoformat(),
                item.incident_id,
            ),
        )
    # Default and "latest": newest publication date first.
    return sorted(incidents, key=publication_key, reverse=True)
