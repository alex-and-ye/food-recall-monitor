from __future__ import annotations

from abc import ABC, abstractmethod

from models.discovery_candidate import (
    CandidateDecision,
    DiscoveryCandidate,
    EarlyWarningQueryState,
)


class EarlyWarningCandidateDBInterface(ABC):
    @abstractmethod
    def upsert_candidate(self, candidate: DiscoveryCandidate) -> DiscoveryCandidate:
        pass

    @abstractmethod
    def get_candidate(self, candidate_id: str) -> DiscoveryCandidate | None:
        pass

    @abstractmethod
    def get_candidate_by_url(self, url: str) -> DiscoveryCandidate | None:
        pass

    @abstractmethod
    def list_candidates(
        self,
        *,
        decision: CandidateDecision | None = None,
        limit: int | None = None,
    ) -> list[DiscoveryCandidate]:
        pass

    @abstractmethod
    def upsert_query_state(self, state: EarlyWarningQueryState) -> EarlyWarningQueryState:
        pass

    @abstractmethod
    def get_query_state(self, query_id: str) -> EarlyWarningQueryState | None:
        pass

    @abstractmethod
    def list_query_states(self) -> list[EarlyWarningQueryState]:
        pass
