"""Early-warning incident models and Chroma serialization helpers.

Defines incident taxonomy, evidence records, create/persist shapes, and
metadata document conversion for the early-warning store.
"""

import json
from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator

class IncidentType(StrEnum):
    """Classification of an early-warning food-safety incident."""

    OFFICIAL_RECALL = "official_recall"
    POTENTIAL_RECALL = "potential_recall"
    FOODBORNE_OUTBREAK = "foodborne_outbreak"
    INVESTIGATION = "investigation"
    COMPANY_WITHDRAWAL = "company_withdrawal"
    PUBLIC_HEALTH_WARNING = "public_health_warning"
    FOOD_SAFETY_ADVISORY = "food_safety_advisory"

class VerificationStatus(StrEnum):
    """How thoroughly an incident has been verified."""

    PENDING = "pending"
    CORROBORATED = "corroborated"
    OFFICIALLY_CONFIRMED = "officially_confirmed"
    DISMISSED = "dismissed"
    SUPERSEDED = "superseded"

class SourceKind(StrEnum):
    """Kind of publisher or channel that produced incident evidence."""

    OFFICIAL_RECALL = "official_recall"
    GOVERNMENT_INVESTIGATION = "government_investigation"
    WHO_FAO = "who_fao"
    COMPANY_RELEASE = "company_release"
    MAJOR_NEWS = "major_news"
    TRADE_PUBLICATION = "trade_publication"
    UNKNOWN = "unknown"
    BLOG = "blog"

class TrustTier(StrEnum):
    """Relative trustworthiness tier assigned to a source."""

    OFFICIAL = "official"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"

class IncidentEvidence(BaseModel):
    """A source record retained as auditable incident evidence."""

    url: str = Field(min_length=1)
    title: str = ""
    publication_date: date | None = None
    source_kind: SourceKind = SourceKind.UNKNOWN
    content_hash: str = ""
    domain: str = ""
    publisher: str = ""
    redirected_url_aliases: list[str] = Field(default_factory=list)

    @field_validator(
        "url",
        "title",
        "content_hash",
        "domain",
        "publisher",
        mode="before",
    )
    @classmethod
    def _strip_text(cls, value: object) -> str:
        """Strip whitespace from string evidence fields."""
        return str(value or "").strip()

    @field_validator("redirected_url_aliases", mode="before")
    @classmethod
    def _normalize_aliases(cls, value: object) -> list[str]:
        """Deduplicate and strip redirected URL aliases."""
        if not isinstance(value, list):
            return []
        return list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))

    def to_chroma_json(self) -> str:
        """Serialize this evidence record to a compact JSON string for Chroma."""
        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    @classmethod
    def from_chroma_json(cls, value: str) -> IncidentEvidence:
        """Deserialize an evidence record from a Chroma JSON string.

        Args:
            value: JSON object string previously produced by ``to_chroma_json``.

        Returns:
            Validated ``IncidentEvidence`` instance.

        Raises:
            ValueError: If the payload is not a JSON object.
        """
        payload = json.loads(value)
        if not isinstance(payload, dict):
            raise ValueError("incident evidence JSON must contain an object")
        return cls.model_validate(payload)

# Concise alias for callers that work with several evidence types.
EvidenceRecord = IncidentEvidence

class EarlyWarningIncidentCreate(BaseModel):
    """Incident payload used when creating a record before an ID is assigned."""

    incident_type: IncidentType
    verification_status: VerificationStatus = VerificationStatus.PENDING
    confidence_score: int = Field(default=0, ge=0, le=100)
    confidence_reasons: list[str] = Field(default_factory=list)
    product_name: str = ""
    company_name: str = ""
    product_category: str = ""
    hazard_type: str = ""
    incident_reason: str = ""
    summary: str = ""
    consumer_guidance: str = ""
    country: str = ""
    affected_regions: list[str] = Field(default_factory=list)
    publication_date: date | None = None
    first_discovered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_discovered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    primary_source_url: str = Field(min_length=1)
    primary_source_domain: str = ""
    primary_publisher: str = ""
    source_kind: SourceKind = SourceKind.UNKNOWN
    trust_tier: TrustTier = TrustTier.UNKNOWN
    original_language: str = ""
    evidence: list[IncidentEvidence] = Field(default_factory=list)
    cluster_fingerprint: str = ""
    linked_official_alert_ids: list[str] = Field(default_factory=list)
    analyst_notes: str = ""
    status_updated_at: datetime | None = None
    extraction_completeness: float = Field(default=0.0, ge=0.0, le=1.0)
    processing_errors: list[str] = Field(default_factory=list)

    @field_validator(
        "product_name",
        "company_name",
        "product_category",
        "hazard_type",
        "incident_reason",
        "summary",
        "consumer_guidance",
        "country",
        "primary_source_url",
        "primary_source_domain",
        "primary_publisher",
        "original_language",
        "cluster_fingerprint",
        "analyst_notes",
        mode="before",
    )
    @classmethod
    def _strip_text(cls, value: object) -> str:
        """Strip whitespace from free-text incident fields."""
        return str(value or "").strip()

    @field_validator(
        "affected_regions",
        "confidence_reasons",
        "linked_official_alert_ids",
        "processing_errors",
        mode="before",
    )
    @classmethod
    def _normalize_strings(cls, value: object) -> list[str]:
        """Deduplicate and strip string-list fields."""
        if not isinstance(value, list):
            return []
        return list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))

    @field_validator("first_discovered_at", "last_discovered_at", mode="after")
    @classmethod
    def _ensure_timezone(cls, value: datetime) -> datetime:
        """Attach UTC when discovery timestamps lack timezone info."""
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    def to_document(self) -> str:
        """Serialize the create payload to a compact JSON document string."""
        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

class EarlyWarningIncident(EarlyWarningIncidentCreate):
    """Persisted early-warning incident with a stable ``incident_id``."""

    incident_id: str = Field(min_length=1)

    def get_id(self) -> str:
        """Return the stable incident identifier."""
        return self.incident_id

    def effective_publication_date(self) -> date:
        """Date used for dashboard sorting/filtering (matches card display)."""
        if self.publication_date is not None:
            return self.publication_date
        discovered = self.first_discovered_at
        if discovered.tzinfo is not None:
            discovered = discovered.astimezone(timezone.utc)
        return discovered.date()

    def to_metadata(self) -> dict[str, str | int | float | bool]:
        """Flatten the incident into Chroma-compatible scalar metadata."""
        metadata: dict[str, str | int | float | bool] = {
            "incident_id": self.incident_id,
            "incident_type": self.incident_type,
            "verification_status": self.verification_status,
            "confidence_score": self.confidence_score,
            "primary_source_url": self.primary_source_url,
            "source_kind": self.source_kind,
            "trust_tier": self.trust_tier,
            "first_discovered_at": self.first_discovered_at.isoformat(),
            "last_discovered_at": self.last_discovered_at.isoformat(),
            "evidence_json": serialize_evidence(self.evidence),
            "confidence_reasons_json": _json_list(self.confidence_reasons),
            "linked_official_alert_ids_json": _json_list(self.linked_official_alert_ids),
            "affected_regions_json": _json_list(self.affected_regions),
            "processing_errors_json": _json_list(self.processing_errors),
            "extraction_completeness": self.extraction_completeness,
        }
        optional_values = {
            "product_name": self.product_name,
            "company_name": self.company_name,
            "product_category": self.product_category,
            "hazard_type": self.hazard_type,
            "incident_reason": self.incident_reason,
            "summary": self.summary,
            "consumer_guidance": self.consumer_guidance,
            "country": self.country,
            "publication_date": self.publication_date.isoformat() if self.publication_date else "",
            "primary_source_domain": self.primary_source_domain,
            "primary_publisher": self.primary_publisher,
            "original_language": self.original_language,
            "cluster_fingerprint": self.cluster_fingerprint,
            "analyst_notes": self.analyst_notes,
            "status_updated_at": self.status_updated_at.isoformat() if self.status_updated_at else "",
        }
        metadata.update({key: value for key, value in optional_values.items() if value})
        return metadata

    @classmethod
    def from_document(cls, document: str) -> EarlyWarningIncident:
        """Deserialize a full incident from a JSON document string.

        Args:
            document: JSON object string for the incident.

        Returns:
            Validated ``EarlyWarningIncident``.

        Raises:
            ValueError: If the payload is not a JSON object.
        """
        payload = json.loads(document)
        if not isinstance(payload, dict):
            raise ValueError("incident document must contain an object")
        return cls.model_validate(payload)

    @classmethod
    def from_metadata(cls, metadata: dict[str, Any]) -> EarlyWarningIncident:
        """Rehydrate an incident from flat Chroma metadata fields.

        Args:
            metadata: Scalar/JSON metadata map previously written by ``to_metadata``.

        Returns:
            Validated ``EarlyWarningIncident``.
        """
        evidence = deserialize_evidence(metadata.get("evidence_json", "[]"))
        return cls(
            incident_id=str(metadata["incident_id"]),
            incident_type=str(metadata["incident_type"]),
            verification_status=str(metadata.get("verification_status") or "pending"),
            confidence_score=int(metadata.get("confidence_score") or 0),
            confidence_reasons=_parse_json_list(metadata.get("confidence_reasons_json")),
            product_name=str(metadata.get("product_name") or ""),
            company_name=str(metadata.get("company_name") or ""),
            product_category=str(metadata.get("product_category") or ""),
            hazard_type=str(metadata.get("hazard_type") or ""),
            incident_reason=str(metadata.get("incident_reason") or ""),
            summary=str(metadata.get("summary") or ""),
            consumer_guidance=str(metadata.get("consumer_guidance") or ""),
            country=str(metadata.get("country") or ""),
            publication_date=_parse_date(metadata.get("publication_date")),
            first_discovered_at=_parse_datetime(metadata.get("first_discovered_at")),
            last_discovered_at=_parse_datetime(metadata.get("last_discovered_at")),
            primary_source_url=str(metadata["primary_source_url"]),
            primary_source_domain=str(metadata.get("primary_source_domain") or ""),
            primary_publisher=str(metadata.get("primary_publisher") or ""),
            source_kind=str(metadata.get("source_kind") or "unknown"),
            trust_tier=str(metadata.get("trust_tier") or "unknown"),
            original_language=str(metadata.get("original_language") or ""),
            evidence=evidence,
            cluster_fingerprint=str(metadata.get("cluster_fingerprint") or ""),
            linked_official_alert_ids=_parse_json_list(
                metadata.get("linked_official_alert_ids_json")
            ),
            affected_regions=_parse_json_list(metadata.get("affected_regions_json")),
            analyst_notes=str(metadata.get("analyst_notes") or ""),
            status_updated_at=_parse_optional_datetime(metadata.get("status_updated_at")),
            extraction_completeness=float(metadata.get("extraction_completeness") or 0.0),
            processing_errors=_parse_json_list(metadata.get("processing_errors_json")),
        )

class IncidentStatusCounts(BaseModel):
    """Aggregate counts of incidents by verification status."""

    pending: int = 0
    corroborated: int = 0
    officially_confirmed: int = 0
    dismissed: int = 0
    superseded: int = 0

class IncidentsVersion(BaseModel):
    """Version token for the incidents collection (count + content fingerprint)."""

    count: int
    fingerprint: str

def serialize_evidence(evidence: list[IncidentEvidence]) -> str:
    """Serialize a list of evidence records to a compact JSON array string.

    Args:
        evidence: Evidence records to serialize.

    Returns:
        Sorted-key JSON array string suitable for Chroma metadata.
    """
    return json.dumps(
        [item.model_dump(mode="json") for item in evidence],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )

def deserialize_evidence(value: object) -> list[IncidentEvidence]:
    """Parse evidence from a JSON string or already-decoded list.

    Args:
        value: JSON string, list of objects, or empty/invalid input.

    Returns:
        List of validated ``IncidentEvidence`` instances.

    Raises:
        ValueError: If a non-list JSON payload is provided.
    """
    if isinstance(value, list):
        payload = value
    elif isinstance(value, str) and value.strip():
        payload = json.loads(value)
    else:
        payload = []
    if not isinstance(payload, list):
        raise ValueError("incident evidence JSON must contain an array")
    return [IncidentEvidence.model_validate(item) for item in payload if isinstance(item, dict)]

def _json_list(values: list[str]) -> str:
    """Serialize a string list to a compact JSON array."""
    return json.dumps(values, ensure_ascii=False, separators=(",", ":"))

def _parse_json_list(value: object) -> list[str]:
    """Parse a string list from a JSON string or pass through a list."""
    if isinstance(value, list):
        return [str(item) for item in value]
    if not isinstance(value, str) or not value.strip():
        return []
    parsed = json.loads(value)
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed]

def _parse_date(value: object) -> date | None:
    """Parse an ISO date string, or return None when empty."""
    text = str(value or "").strip()
    return date.fromisoformat(text) if text else None

def _parse_datetime(value: object) -> datetime:
    """Parse an ISO datetime string, or default to now (UTC) when empty."""
    text = str(value or "").strip()
    return datetime.fromisoformat(text) if text else datetime.now(timezone.utc)

def _parse_optional_datetime(value: object) -> datetime | None:
    """Parse an optional ISO datetime string, or return None when empty."""
    text = str(value or "").strip()
    return datetime.fromisoformat(text) if text else None
