"""Discovery candidates and early-warning query state models.

Tracks web-search hits through acceptance, fetch, classification, and
conversion into early-warning incidents.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator

from models.search_candidate import SearchCandidate, SearchQuery, canonicalize_url, stable_search_id

class CandidateDecision(StrEnum):
    """LLM triage outcome for a discovered search result."""

    ACCEPT = "accept"
    REJECT = "reject"
    BORDERLINE = "borderline"

class CandidateStatus(StrEnum):
    """Processing lifecycle status of a discovery candidate."""

    DISCOVERED = "discovered"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    FETCH_FAILED = "fetch_failed"
    CLASSIFIED = "classified"
    CONVERTED = "converted"
    RETRYABLE = "retryable"
    UNSUPPORTED_CONTENT = "unsupported_content"

class DiscoveryCandidate(BaseModel):
    """A URL discovered via search and tracked through early-warning processing."""

    candidate_id: str = ""
    canonical_url: str
    title: str
    description: str = ""
    country: str
    language: str
    decision: CandidateDecision
    confidence: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)
    query_ids: list[str] = Field(default_factory=list)
    first_seen_at: datetime
    last_seen_at: datetime
    processing_status: CandidateStatus = CandidateStatus.DISCOVERED
    attempt_count: int = Field(default=0, ge=0)
    next_retry_at: datetime | None = None
    last_error: str = ""
    content_hash: str = ""
    final_url: str = ""
    linked_incident_id: str = ""

    @field_validator("canonical_url", mode="before")
    @classmethod
    def _canonicalize_url(cls, value: object) -> str:
        """Normalize the candidate URL to a canonical form."""
        return canonicalize_url(str(value))

    @field_validator("first_seen_at", "last_seen_at")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        """Attach UTC when a datetime lacks timezone info."""
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    @field_validator("next_retry_at")
    @classmethod
    def _normalize_optional_timezone(cls, value: datetime | None) -> datetime | None:
        """Attach UTC to an optional retry timestamp when missing."""
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    @field_validator("final_url", mode="before")
    @classmethod
    def _canonicalize_final_url(cls, value: object) -> str:
        """Canonicalize a non-empty final (post-redirect) URL."""
        text = str(value or "").strip()
        return canonicalize_url(text) if text else ""

    @model_validator(mode="after")
    def _ensure_candidate_id(self) -> DiscoveryCandidate:
        """Derive a stable ID from the URL and validate seen-at ordering."""
        if not self.candidate_id.strip():
            self.candidate_id = stable_search_id(self.canonical_url)
        if self.last_seen_at < self.first_seen_at:
            raise ValueError("last_seen_at must not be earlier than first_seen_at")
        return self

    @classmethod
    def from_search(
        cls,
        candidate: SearchCandidate,
        *,
        decision: CandidateDecision,
        confidence: float,
        reasons: list[str],
        seen_at: datetime | None = None,
    ) -> DiscoveryCandidate:
        """Build a discovery candidate from a search hit and triage decision.

        Args:
            candidate: Raw search result to promote.
            decision: Accept / reject / borderline triage outcome.
            confidence: Model confidence in the decision (0–1).
            reasons: Human-readable justification strings.
            seen_at: Observation time; defaults to now (UTC).

        Returns:
            A new ``DiscoveryCandidate`` with status derived from ``decision``.
        """
        timestamp = seen_at or datetime.now(timezone.utc)
        canonical_url = canonicalize_url(candidate.url)
        return cls(
            candidate_id=stable_search_id(canonical_url),
            canonical_url=canonical_url,
            title=candidate.title,
            description=candidate.description,
            country=candidate.country,
            language=candidate.language,
            decision=decision,
            confidence=confidence,
            reasons=reasons,
            query_ids=[candidate.query_id],
            first_seen_at=timestamp,
            last_seen_at=timestamp,
            processing_status=(
                CandidateStatus.ACCEPTED
                if decision == CandidateDecision.ACCEPT
                else CandidateStatus.REJECTED
                if decision == CandidateDecision.REJECT
                else CandidateStatus.DISCOVERED
            ),
        )

    def merge_observation(self, other: DiscoveryCandidate) -> DiscoveryCandidate:
        """Merge a re-observation of the same candidate into one record.

        Combines query IDs, prefers the stronger triage decision, and preserves
        terminal or retryable processing state when appropriate.

        Args:
            other: Another observation of the same ``candidate_id``.

        Returns:
            A merged ``DiscoveryCandidate``.

        Raises:
            ValueError: If the candidate IDs differ.
        """
        if self.candidate_id != other.candidate_id:
            raise ValueError("cannot merge candidates with different IDs")
        query_ids = list(dict.fromkeys([*self.query_ids, *other.query_ids]))
        terminal_statuses = {
            CandidateStatus.CLASSIFIED,
            CandidateStatus.CONVERTED,
            CandidateStatus.FETCH_FAILED,
            CandidateStatus.UNSUPPORTED_CONTENT,
            CandidateStatus.REJECTED,
        }
        incoming_is_processing_update = (
            other.processing_status != self.processing_status
            and other.last_seen_at <= self.last_seen_at
        ) or (
            other.attempt_count > self.attempt_count
            or bool(other.content_hash and other.content_hash != self.content_hash)
            or bool(other.final_url and other.final_url != self.final_url)
        )
        preserve_terminal = self.processing_status in terminal_statuses
        decision = (
            other.decision
            if incoming_is_processing_update and not preserve_terminal
            else _stronger_decision(self.decision, other.decision)
        )
        winner = self if decision == self.decision else other
        preserve_processing = (
            preserve_terminal
            or (
                self.processing_status == CandidateStatus.RETRYABLE
                and not incoming_is_processing_update
            )
        )
        processing_source = self if preserve_processing else other
        return other.model_copy(
            update={
                "decision": decision,
                "confidence": winner.confidence,
                "reasons": winner.reasons,
                "query_ids": query_ids,
                "first_seen_at": min(self.first_seen_at, other.first_seen_at),
                "last_seen_at": max(self.last_seen_at, other.last_seen_at),
                "processing_status": processing_source.processing_status,
                "attempt_count": max(self.attempt_count, other.attempt_count),
                "next_retry_at": processing_source.next_retry_at,
                "last_error": processing_source.last_error,
                "content_hash": self.content_hash or other.content_hash,
                "final_url": self.final_url or other.final_url,
                "linked_incident_id": self.linked_incident_id or other.linked_incident_id,
            }
        )

    def mark_status(
        self,
        status: CandidateStatus,
        *,
        error: str = "",
        next_retry_at: datetime | None = None,
        content_hash: str | None = None,
        final_url: str | None = None,
        linked_incident_id: str | None = None,
        increment_attempt: bool = False,
    ) -> DiscoveryCandidate:
        """Return a copy with an updated processing status and related fields.

        Args:
            status: New processing status.
            error: Optional last-error message.
            next_retry_at: Optional scheduled retry time.
            content_hash: Optional content fingerprint to store.
            final_url: Optional post-redirect URL to store.
            linked_incident_id: Optional linked incident identifier.
            increment_attempt: Whether to increment ``attempt_count``.

        Returns:
            Updated ``DiscoveryCandidate`` copy.
        """
        updates: dict[str, object] = {
            "processing_status": status,
            "last_error": error.strip(),
            "next_retry_at": next_retry_at,
            "attempt_count": self.attempt_count + (1 if increment_attempt else 0),
        }
        if content_hash is not None:
            updates["content_hash"] = content_hash.strip().lower()
        if final_url is not None:
            updates["final_url"] = final_url
        if linked_incident_id is not None:
            updates["linked_incident_id"] = linked_incident_id.strip()
        return self.model_copy(update=updates)

class EarlyWarningQueryState(BaseModel):
    """Persistent pagination and scheduling state for one search query."""

    query: SearchQuery
    last_searched_at: datetime | None = None
    next_offset: int = Field(default=0, ge=0, le=9)
    search_count: int = Field(default=0, ge=0)

    @field_validator("last_searched_at")
    @classmethod
    def _normalize_timezone(cls, value: datetime | None) -> datetime | None:
        """Attach UTC when an optional last-searched timestamp lacks tzinfo."""
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    @property
    def query_id(self) -> str:
        """Stable identifier of the underlying search query."""
        return self.query.query_id

    def record_search(
        self,
        *,
        searched_at: datetime | None = None,
        next_offset: int | None = None,
    ) -> EarlyWarningQueryState:
        """Record that a search was executed and advance pagination state.

        Args:
            searched_at: Search time; defaults to now (UTC).
            next_offset: New offset to store; keeps current when omitted.

        Returns:
            Updated query state with incremented ``search_count``.
        """
        return self.model_copy(
            update={
                "last_searched_at": searched_at or datetime.now(timezone.utc),
                "next_offset": self.next_offset if next_offset is None else next_offset,
                "search_count": self.search_count + 1,
            }
        )

# Rank for picking the stronger triage decision when merging observations.
_DECISION_RANK = {
    CandidateDecision.REJECT: 0,
    CandidateDecision.BORDERLINE: 1,
    CandidateDecision.ACCEPT: 2,
}

def _stronger_decision(
    left: CandidateDecision,
    right: CandidateDecision,
) -> CandidateDecision:
    """Return the stronger of two triage decisions (accept > borderline > reject)."""
    return left if _DECISION_RANK[left] >= _DECISION_RANK[right] else right
