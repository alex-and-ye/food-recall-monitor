from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from db.chroma_early_warning_candidates import (
    EarlyWarningCandidatesChromaClient,
    InMemoryEarlyWarningCandidateStore,
)
from models.discovery_candidate import (
    CandidateDecision,
    CandidateStatus,
    DiscoveryCandidate,
    EarlyWarningQueryState,
)
from models.search_candidate import SearchQuery


def _candidate(
    *,
    seen_at: datetime,
    query_id: str,
    decision: CandidateDecision = CandidateDecision.BORDERLINE,
) -> DiscoveryCandidate:
    return DiscoveryCandidate(
        candidate_id="candidate-1",
        canonical_url="https://example.com/recall?utm_source=test",
        title="Food recall",
        description="Food safety notice",
        country="CA",
        language="en",
        decision=decision,
        confidence=0.6,
        reasons=["recall term: food recall"],
        query_ids=[query_id],
        first_seen_at=seen_at,
        last_seen_at=seen_at,
    )


class InMemoryEarlyWarningCandidateStoreTests(unittest.TestCase):
    def test_upsert_merges_query_ids_and_observation_times(self) -> None:
        store = InMemoryEarlyWarningCandidateStore()
        first_seen = datetime(2026, 7, 21, tzinfo=timezone.utc)
        later = first_seen + timedelta(days=1)

        store.upsert_candidate(_candidate(seen_at=first_seen, query_id="query-1"))
        stored = store.upsert_candidate(
            _candidate(
                seen_at=later,
                query_id="query-2",
                decision=CandidateDecision.ACCEPT,
            )
        )

        self.assertEqual(stored.query_ids, ["query-1", "query-2"])
        self.assertEqual(stored.first_seen_at, first_seen)
        self.assertEqual(stored.last_seen_at, later)
        self.assertEqual(stored.decision, CandidateDecision.ACCEPT)
        self.assertEqual(
            store.get_candidate_by_url("https://example.com/recall#fragment"),
            stored,
        )

    def test_upsert_keeps_stronger_decision_on_rediscovery(self) -> None:
        store = InMemoryEarlyWarningCandidateStore()
        now = datetime.now(timezone.utc)
        store.upsert_candidate(
            _candidate(
                seen_at=now,
                query_id="query-1",
                decision=CandidateDecision.ACCEPT,
            )
        )
        stored = store.upsert_candidate(
            _candidate(
                seen_at=now + timedelta(hours=1),
                query_id="query-2",
                decision=CandidateDecision.REJECT,
            )
        )

        self.assertEqual(stored.decision, CandidateDecision.ACCEPT)
        self.assertEqual(stored.query_ids, ["query-1", "query-2"])

    def test_lists_by_decision_and_limit(self) -> None:
        store = InMemoryEarlyWarningCandidateStore()
        now = datetime.now(timezone.utc)
        accepted = _candidate(
            seen_at=now,
            query_id="query-1",
            decision=CandidateDecision.ACCEPT,
        )
        rejected = _candidate(
            seen_at=now - timedelta(hours=1),
            query_id="query-2",
            decision=CandidateDecision.REJECT,
        ).model_copy(update={"candidate_id": "candidate-2", "canonical_url": "https://example.com/2"})
        store.upsert_candidate(accepted)
        store.upsert_candidate(rejected)

        self.assertEqual(
            store.list_candidates(decision=CandidateDecision.ACCEPT),
            [accepted],
        )
        self.assertEqual(store.list_candidates(limit=1), [accepted])

    def test_persists_query_rotation_state(self) -> None:
        store = InMemoryEarlyWarningCandidateStore()
        query = SearchQuery.create(
            text='"food recall" Canada',
            country="CA",
            language="en",
        )
        state = EarlyWarningQueryState(query=query)
        searched = state.record_search(next_offset=1)

        store.upsert_query_state(searched)

        self.assertEqual(store.get_query_state(query.query_id), searched)
        self.assertEqual(store.list_query_states(), [searched])
        self.assertEqual(searched.search_count, 1)
        self.assertEqual(searched.next_offset, 1)

    def test_terminal_processing_state_survives_new_search_observation(self) -> None:
        store = InMemoryEarlyWarningCandidateStore()
        now = datetime.now(timezone.utc)
        converted = _candidate(
            seen_at=now,
            query_id="query-1",
            decision=CandidateDecision.ACCEPT,
        ).mark_status(
            CandidateStatus.CONVERTED,
            content_hash="abc123",
            linked_incident_id="incident-1",
        )
        store.upsert_candidate(converted)

        refreshed = store.upsert_candidate(
            _candidate(
                seen_at=now + timedelta(hours=1),
                query_id="query-2",
                decision=CandidateDecision.BORDERLINE,
            )
        )

        self.assertEqual(refreshed.processing_status, CandidateStatus.CONVERTED)
        self.assertEqual(refreshed.content_hash, "abc123")
        self.assertEqual(refreshed.linked_incident_id, "incident-1")

    def test_processing_update_replaces_prior_accepted_state(self) -> None:
        store = InMemoryEarlyWarningCandidateStore()
        now = datetime.now(timezone.utc)
        accepted = _candidate(
            seen_at=now,
            query_id="query-1",
            decision=CandidateDecision.ACCEPT,
        )
        stored = store.upsert_candidate(accepted)

        converted = store.upsert_candidate(
            stored.mark_status(
                CandidateStatus.CONVERTED,
                content_hash="abc123",
                linked_incident_id="incident-1",
            )
        )

        self.assertEqual(converted.processing_status, CandidateStatus.CONVERTED)
        self.assertEqual(converted.linked_incident_id, "incident-1")

    def test_explicit_listing_rejection_replaces_accepted_decision(self) -> None:
        store = InMemoryEarlyWarningCandidateStore()
        now = datetime.now(timezone.utc)
        accepted = store.upsert_candidate(
            _candidate(
                seen_at=now,
                query_id="query-1",
                decision=CandidateDecision.ACCEPT,
            ).mark_status(CandidateStatus.ACCEPTED, content_hash="listing-hash")
        )

        rejected = store.upsert_candidate(
            accepted.mark_status(CandidateStatus.CLASSIFIED).model_copy(
                update={"decision": CandidateDecision.REJECT}
            )
        )

        self.assertEqual(rejected.processing_status, CandidateStatus.CLASSIFIED)
        self.assertEqual(rejected.decision, CandidateDecision.REJECT)


class ChromaEarlyWarningCandidateTests(unittest.TestCase):
    def test_init_creates_candidate_and_query_collections(self) -> None:
        fake_client = MagicMock()
        candidate_collection = object()
        query_collection = object()
        fake_client.get_or_create_collection.side_effect = [
            candidate_collection,
            query_collection,
        ]

        with patch(
            "db.chroma_early_warning_candidates.chromadb.HttpClient",
            return_value=fake_client,
        ) as http_client:
            client = EarlyWarningCandidatesChromaClient(host="chroma", port=9000)

        http_client.assert_called_once_with(host="chroma", port=9000)
        self.assertEqual(
            fake_client.get_or_create_collection.call_args_list[0].kwargs["name"],
            EarlyWarningCandidatesChromaClient.CANDIDATE_COLLECTION_NAME,
        )
        self.assertEqual(
            fake_client.get_or_create_collection.call_args_list[1].kwargs["name"],
            EarlyWarningCandidatesChromaClient.QUERY_COLLECTION_NAME,
        )
        self.assertIs(client.candidate_collection, candidate_collection)
        self.assertIs(client.query_collection, query_collection)

    def test_query_metadata_omits_empty_timestamp(self) -> None:
        client = object.__new__(EarlyWarningCandidatesChromaClient)
        client.query_collection = MagicMock()
        query = SearchQuery.create(
            text='"food recall" Canada',
            country="CA",
            language="en",
        )

        client.upsert_query_state(EarlyWarningQueryState(query=query))

        metadata = client.query_collection.upsert.call_args.kwargs["metadatas"][0]
        self.assertNotIn("last_searched_at", metadata)
        self.assertNotIn("", metadata.values())


if __name__ == "__main__":
    unittest.main()
