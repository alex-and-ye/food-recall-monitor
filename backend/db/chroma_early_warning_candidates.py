"""ChromaDB and in-memory stores for early-warning discovery candidates.

Persists discovery candidates and per-query search state used by the
early-warning pipeline, with an in-memory test double sharing the same API.
"""

import json
from typing import cast

import chromadb
from chromadb.api.types import Metadata

from db.early_warning_candidate_interface import EarlyWarningCandidateDBInterface
from models.discovery_candidate import (
    CandidateDecision,
    DiscoveryCandidate,
    EarlyWarningQueryState,
)
from models.search_candidate import canonicalize_url

class EarlyWarningCandidatesChromaClient(EarlyWarningCandidateDBInterface):
    """Chroma-backed store for discovery candidates and query state."""

    # Chroma collection for early-warning discovery candidates
    CANDIDATE_COLLECTION_NAME = "early_warning_candidates_collection"
    # Chroma collection for early-warning search query pagination state
    QUERY_COLLECTION_NAME = "early_warning_queries_collection"

    def __init__(self, host: str, port: int) -> None:
        """Connect to Chroma and ensure candidate/query collections exist.

        Args:
            host: Chroma HTTP host.
            port: Chroma HTTP port.
        """
        self.client = chromadb.HttpClient(host=host, port=port)
        self.candidate_collection = self.client.get_or_create_collection(
            name=self.CANDIDATE_COLLECTION_NAME
        )
        self.query_collection = self.client.get_or_create_collection(
            name=self.QUERY_COLLECTION_NAME
        )

    def upsert_candidate(self, candidate: DiscoveryCandidate) -> DiscoveryCandidate:
        """Insert or merge a candidate, reusing ID when URL already exists.

        Args:
            candidate: Candidate observation to store or merge.

        Returns:
            The stored candidate after merge/upsert.
        """
        existing = self.get_candidate(candidate.candidate_id) or self.get_candidate_by_url(
            candidate.canonical_url
        )
        if existing is not None and existing.candidate_id != candidate.candidate_id:
            candidate = candidate.model_copy(update={"candidate_id": existing.candidate_id})
        stored = existing.merge_observation(candidate) if existing is not None else candidate
        metadata_values: dict[str, str | int | float | bool] = {
            "candidate_id": stored.candidate_id,
            "canonical_url": stored.canonical_url,
            "country": stored.country,
            "language": stored.language,
            "decision": stored.decision,
            "confidence": stored.confidence,
            "first_seen_at": stored.first_seen_at.isoformat(),
            "last_seen_at": stored.last_seen_at.isoformat(),
            "processing_status": stored.processing_status,
            "attempt_count": stored.attempt_count,
        }
        if stored.next_retry_at is not None:
            metadata_values["next_retry_at"] = stored.next_retry_at.isoformat()
        if stored.content_hash:
            metadata_values["content_hash"] = stored.content_hash
        if stored.final_url:
            metadata_values["final_url"] = stored.final_url
        if stored.linked_incident_id:
            metadata_values["linked_incident_id"] = stored.linked_incident_id
        metadata = cast(Metadata, metadata_values)
        self.candidate_collection.upsert(
            ids=[stored.candidate_id],
            documents=[json.dumps(stored.model_dump(mode="json"), ensure_ascii=False)],
            metadatas=[metadata],
        )
        return stored

    def get_candidate(self, candidate_id: str) -> DiscoveryCandidate | None:
        """Fetch a candidate by ID from Chroma.

        Args:
            candidate_id: Unique candidate ID.

        Returns:
            Parsed candidate, or None if missing/blank/unparsable.
        """
        key = candidate_id.strip()
        if not key:
            return None
        results = self.candidate_collection.get(ids=[key], include=["documents"])
        documents = results.get("documents") or []
        return _parse_candidate(documents[0] if documents else None)

    def get_candidate_by_url(self, url: str) -> DiscoveryCandidate | None:
        """Fetch a candidate by canonicalized URL metadata.

        Args:
            url: Source URL to look up.

        Returns:
            Parsed candidate, or None if not found.
        """
        canonical_url = canonicalize_url(url)
        results = self.candidate_collection.get(
            where={"canonical_url": canonical_url},
            include=["documents"],
        )
        documents = results.get("documents") or []
        return _parse_candidate(documents[0] if documents else None)

    def list_candidates(
        self,
        *,
        decision: CandidateDecision | None = None,
        limit: int | None = None,
    ) -> list[DiscoveryCandidate]:
        """List candidates filtered by decision, newest last_seen_at first.

        Args:
            decision: Optional decision filter.
            limit: Max results; None for unlimited.

        Returns:
            Matching candidates.

        Raises:
            ValueError: If limit is negative.
        """
        if limit is not None and limit < 0:
            raise ValueError("limit must be non-negative")
        where = {"decision": decision.value} if decision is not None else None
        kwargs: dict[str, object] = {"include": ["documents"]}
        if where is not None:
            kwargs["where"] = where
        results = self.candidate_collection.get(**kwargs)
        candidates = [
            candidate
            for document in results.get("documents") or []
            if (candidate := _parse_candidate(document)) is not None
        ]
        candidates.sort(key=lambda item: (item.last_seen_at, item.candidate_id), reverse=True)
        return candidates if limit is None else candidates[:limit]

    def upsert_query_state(self, state: EarlyWarningQueryState) -> EarlyWarningQueryState:
        """Insert or replace search-query pagination state in Chroma.

        Args:
            state: Query state to persist.

        Returns:
            The same state object after upsert.
        """
        metadata_values: dict[str, str | int | float | bool] = {
            "query_id": state.query_id,
            "country": state.query.country,
            "language": state.query.language,
            "next_offset": state.next_offset,
            "search_count": state.search_count,
        }
        if state.last_searched_at is not None:
            metadata_values["last_searched_at"] = state.last_searched_at.isoformat()
        metadata = cast(Metadata, metadata_values)
        self.query_collection.upsert(
            ids=[state.query_id],
            documents=[json.dumps(state.model_dump(mode="json"), ensure_ascii=False)],
            metadatas=[metadata],
        )
        return state

    def get_query_state(self, query_id: str) -> EarlyWarningQueryState | None:
        """Fetch query state by ID from Chroma.

        Args:
            query_id: Unique query state ID.

        Returns:
            Parsed state, or None if missing/blank/unparsable.
        """
        key = query_id.strip()
        if not key:
            return None
        results = self.query_collection.get(ids=[key], include=["documents"])
        documents = results.get("documents") or []
        return _parse_query_state(documents[0] if documents else None)

    def list_query_states(self) -> list[EarlyWarningQueryState]:
        """Return all query states sorted by query_id.

        Returns:
            All successfully parsed query states.
        """
        results = self.query_collection.get(include=["documents"])
        states = [
            state
            for document in results.get("documents") or []
            if (state := _parse_query_state(document)) is not None
        ]
        states.sort(key=lambda item: item.query_id)
        return states

class InMemoryEarlyWarningCandidateStore(EarlyWarningCandidateDBInterface):
    """Test double for candidate and query-state persistence."""

    def __init__(self) -> None:
        """Initialize empty in-memory candidate and query-state maps."""
        self._candidates: dict[str, DiscoveryCandidate] = {}
        self._query_states: dict[str, EarlyWarningQueryState] = {}

    def upsert_candidate(self, candidate: DiscoveryCandidate) -> DiscoveryCandidate:
        """Insert or merge a candidate in memory.

        Args:
            candidate: Candidate observation to store or merge.

        Returns:
            The stored candidate after merge/upsert.
        """
        existing = self._candidates.get(candidate.candidate_id) or self.get_candidate_by_url(
            candidate.canonical_url
        )
        if existing is not None and existing.candidate_id != candidate.candidate_id:
            candidate = candidate.model_copy(update={"candidate_id": existing.candidate_id})
        stored = existing.merge_observation(candidate) if existing is not None else candidate
        self._candidates[stored.candidate_id] = stored
        return stored

    def get_candidate(self, candidate_id: str) -> DiscoveryCandidate | None:
        """Fetch a candidate by ID from the in-memory map.

        Args:
            candidate_id: Unique candidate ID.

        Returns:
            Matching candidate, or None if not found.
        """
        return self._candidates.get(candidate_id.strip())

    def get_candidate_by_url(self, url: str) -> DiscoveryCandidate | None:
        """Fetch a candidate by canonicalized URL from memory.

        Args:
            url: Source URL to look up.

        Returns:
            Matching candidate, or None if not found.
        """
        canonical_url = canonicalize_url(url)
        return next(
            (
                candidate
                for candidate in self._candidates.values()
                if candidate.canonical_url == canonical_url
            ),
            None,
        )

    def list_candidates(
        self,
        *,
        decision: CandidateDecision | None = None,
        limit: int | None = None,
    ) -> list[DiscoveryCandidate]:
        """List in-memory candidates, optionally filtered and limited.

        Args:
            decision: Optional decision filter.
            limit: Max results; None for unlimited.

        Returns:
            Matching candidates, newest last_seen_at first.

        Raises:
            ValueError: If limit is negative.
        """
        if limit is not None and limit < 0:
            raise ValueError("limit must be non-negative")
        candidates = list(self._candidates.values())
        if decision is not None:
            candidates = [candidate for candidate in candidates if candidate.decision == decision]
        candidates.sort(key=lambda item: (item.last_seen_at, item.candidate_id), reverse=True)
        return candidates if limit is None else candidates[:limit]

    def upsert_query_state(self, state: EarlyWarningQueryState) -> EarlyWarningQueryState:
        """Insert or replace query state in memory.

        Args:
            state: Query state to persist.

        Returns:
            The stored state.
        """
        self._query_states[state.query_id] = state
        return state

    def get_query_state(self, query_id: str) -> EarlyWarningQueryState | None:
        """Fetch query state by ID from memory.

        Args:
            query_id: Unique query state ID.

        Returns:
            Matching state, or None if not found.
        """
        return self._query_states.get(query_id.strip())

    def list_query_states(self) -> list[EarlyWarningQueryState]:
        """Return all in-memory query states sorted by query_id.

        Returns:
            All stored query states.
        """
        return sorted(self._query_states.values(), key=lambda item: item.query_id)

def _parse_candidate(document: str | None) -> DiscoveryCandidate | None:
    """Deserialize a DiscoveryCandidate from a Chroma document JSON string.

    Args:
        document: Raw JSON document, or None.

    Returns:
        Validated candidate, or None on empty/invalid input.
    """
    if not document:
        return None
    try:
        payload = json.loads(document)
        return DiscoveryCandidate.model_validate(payload)
    except (json.JSONDecodeError, ValueError):
        return None

def _parse_query_state(document: str | None) -> EarlyWarningQueryState | None:
    """Deserialize an EarlyWarningQueryState from a Chroma document JSON string.

    Args:
        document: Raw JSON document, or None.

    Returns:
        Validated query state, or None on empty/invalid input.
    """
    if not document:
        return None
    try:
        payload = json.loads(document)
        return EarlyWarningQueryState.model_validate(payload)
    except (json.JSONDecodeError, ValueError):
        return None
