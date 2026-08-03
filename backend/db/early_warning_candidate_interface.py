"""Abstract persistence contract for early-warning discovery candidates.

Defines the repository interface for candidate documents and per-query
search state used by the early-warning discovery pipeline.
"""

from abc import ABC, abstractmethod

from models.discovery_candidate import (
    CandidateDecision,
    DiscoveryCandidate,
    EarlyWarningQueryState,
)

class EarlyWarningCandidateDBInterface(ABC):
    """Repository interface for discovery candidates and query state."""

    @abstractmethod
    def upsert_candidate(self, candidate: DiscoveryCandidate) -> DiscoveryCandidate:
        """Insert or merge a discovery candidate observation.

        Args:
            candidate: Candidate payload to store or merge with an existing record.

        Returns:
            The stored candidate after merge/upsert.
        """
        pass

    @abstractmethod
    def get_candidate(self, candidate_id: str) -> DiscoveryCandidate | None:
        """Fetch a candidate by its identifier.

        Args:
            candidate_id: Unique candidate ID.

        Returns:
            The matching candidate, or None if not found.
        """
        pass

    @abstractmethod
    def get_candidate_by_url(self, url: str) -> DiscoveryCandidate | None:
        """Fetch a candidate by canonical URL.

        Args:
            url: Source URL (will be canonicalized by implementations).

        Returns:
            The matching candidate, or None if not found.
        """
        pass

    @abstractmethod
    def list_candidates(
        self,
        *,
        decision: CandidateDecision | None = None,
        limit: int | None = None,
    ) -> list[DiscoveryCandidate]:
        """List candidates, optionally filtered by decision.

        Args:
            decision: If set, only return candidates with this decision.
            limit: Maximum number of candidates to return; None for no limit.

        Returns:
            Candidates ordered by most recently seen first.

        Raises:
            ValueError: If limit is negative.
        """
        pass

    @abstractmethod
    def upsert_query_state(self, state: EarlyWarningQueryState) -> EarlyWarningQueryState:
        """Insert or replace search-query pagination state.

        Args:
            state: Query state to persist.

        Returns:
            The stored query state.
        """
        pass

    @abstractmethod
    def get_query_state(self, query_id: str) -> EarlyWarningQueryState | None:
        """Fetch query state by identifier.

        Args:
            query_id: Unique query state ID.

        Returns:
            The matching state, or None if not found.
        """
        pass

    @abstractmethod
    def list_query_states(self) -> list[EarlyWarningQueryState]:
        """Return all stored early-warning query states.

        Returns:
            All query states, typically sorted by query_id.
        """
        pass
