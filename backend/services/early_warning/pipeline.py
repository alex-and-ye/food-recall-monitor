"""Orchestrate early-warning discovery: search, review, scrape, and persist.

Runs Brave Search queries, LLM borderline review, page ingestion, listing
expansion, AI structuring, incident save/merge, and optional official
verification under a shared pipeline lock.
"""

import asyncio
import logging
import re
import unicodedata
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit

import httpx

from config.early_warning import EarlyWarningConfig
from db.early_warning_candidate_interface import EarlyWarningCandidateDBInterface
from models.discovery_candidate import (
    CandidateDecision,
    CandidateStatus,
    DiscoveryCandidate,
    EarlyWarningQueryState,
)
from models.early_warning_incident import EarlyWarningIncident, SourceKind, TrustTier
from models.pipeline_progress import PipelineStage, ProgressReporter
from models.pipeline_warning import WarningCategory
from models.pipeline_run_log import PipelineKind
from models.scraped_record import ScrapedRecallRecord
from services.alert_events import AlertChangeBroadcaster
from services.early_warning.brave_search import BraveSearchClient
from services.early_warning.graph import EarlyWarningProcessingService
from services.early_warning.incidents import EarlyWarningIncidentService
from services.early_warning.ingestion import (
    UnsupportedContentError,
    ingest_early_warning_url,
)
from services.early_warning.query_generator import QueryGenerator
from services.early_warning.verification import IncidentVerificationService
from services.pipeline_progress import PipelineProgressTracker
from services.warnings import WarningsService

LOGGER = logging.getLogger(__name__)  # Module logger for run warnings and progress.
IngestCallable = Callable[..., Awaitable[ScrapedRecallRecord]]  # Injectable URL ingest function.
MAX_LISTING_DETAIL_LINKS = 25  # Cap on detail links fetched from a listing page.
_LISTING_TITLE_SIGNALS = (  # Title/path tokens that indicate a listing/index page.
    "recalls",
    "recall alerts",
    "food alerts",
    "food warnings",
    "latest warnings",
    "product warnings",
    "rappels",
    "alertes",
    "warnungen",
    "produktwarnungen",
)


@dataclass
class EarlyWarningRunResult:
    """Aggregate metrics for one early-warning pipeline run.

    Attributes:
        dry_run: Whether the run stopped after search/queue without scraping.
        queries_searched: Number of Brave Search requests issued.
        search_results: Total raw search result count.
        candidates_accepted: Candidates accepted by LLM review.
        candidates_borderline: Candidates queued as borderline for review.
        candidates_rejected: Candidates rejected by LLM review.
        pages_scraped: Successfully ingested pages.
        records_processed: Pages sent through AI structuring.
        irrelevant_pages: Pages classified irrelevant or out of country scope.
        incidents_saved: Incident upserts performed.
        new_incidents: Upserts that increased the store count.
        officially_confirmed: Incidents confirmed against official recalls.
        skipped_due_to_overlap: Reserved flag for overlap-skip scenarios.
        failures: Map of failing key (URL/query) to error message.
    """

    dry_run: bool = False
    queries_searched: int = 0
    search_results: int = 0
    candidates_accepted: int = 0
    candidates_borderline: int = 0
    candidates_rejected: int = 0
    pages_scraped: int = 0
    records_processed: int = 0
    irrelevant_pages: int = 0
    incidents_saved: int = 0
    new_incidents: int = 0
    officially_confirmed: int = 0
    skipped_due_to_overlap: bool = False
    failures: dict[str, str] = field(default_factory=dict)


class EarlyWarningPipelineService:
    """End-to-end early-warning discovery and persistence pipeline."""

    def __init__(
        self,
        *,
        config: EarlyWarningConfig,
        search_client: BraveSearchClient | None,
        candidate_store: EarlyWarningCandidateDBInterface,
        incident_service: EarlyWarningIncidentService,
        processing_service: EarlyWarningProcessingService,
        verification_service: IncidentVerificationService | None = None,
        broadcaster: AlertChangeBroadcaster | None = None,
        warnings_service: WarningsService | None = None,
        ingest: IngestCallable = ingest_early_warning_url,
        reporter: ProgressReporter | None = None,
        progress_tracker: PipelineProgressTracker | None = None,
        run_lock: asyncio.Lock | None = None,
    ) -> None:
        """Wire discovery, processing, and side-effect dependencies.

        Args:
            config: Early-warning feature and budget configuration.
            search_client: Brave Search client, or None when unavailable.
            candidate_store: Persistence for discovery candidates and query state.
            incident_service: Incident save/merge service.
            processing_service: LLM translate/classify/extract service.
            verification_service: Optional official-recall linker.
            broadcaster: Optional change notifier for new incidents.
            warnings_service: Optional operational warnings sink.
            ingest: Callable used to fetch and normalize page URLs.
            reporter: Optional progress reporter (may be replaced per run).
            progress_tracker: Optional run lifecycle tracker.
            run_lock: Optional lock shared with the official pipeline.
        """
        self.config = config
        self.search_client = search_client
        self.candidate_store = candidate_store
        self.incident_service = incident_service
        self.processing_service = processing_service
        self.verification_service = verification_service
        self.broadcaster = broadcaster
        self.warnings_service = warnings_service
        self.ingest = ingest
        self.reporter = reporter
        self.progress_tracker = progress_tracker
        self.run_lock = run_lock
        self._active_run_id: str | None = None

    async def run(self, *, dry_run: bool = False) -> EarlyWarningRunResult:
        """Run the pipeline, acquiring ``run_lock`` when configured.

        Args:
            dry_run: When True, stop after search/queue without scraping.

        Returns:
            EarlyWarningRunResult with run metrics.

        Raises:
            Exception: Propagates hard pipeline failures after fail_run/warnings.
        """
        if self.run_lock is None:
            return await self._run(dry_run=dry_run)
        # Share the process-wide pipeline lock with the official pipeline so only
        # one heavy run executes at a time. Wait (do not skip) when the lock is
        # held — otherwise empty-DB bootstrap / co-scheduled daily runs never run.
        async with self.run_lock:
            return await self._run(dry_run=dry_run)

    async def _run(self, *, dry_run: bool = False) -> EarlyWarningRunResult:
        """Execute one early-warning discovery run.

        Args:
            dry_run: When True, return after search without scraping/processing.

        Returns:
            Populated EarlyWarningRunResult.

        Raises:
            RuntimeError: When early warning is enabled but Brave Search is missing.
            Exception: On hard failure after progress/warning updates.
        """
        if not self.config.enabled:
            return EarlyWarningRunResult(dry_run=dry_run)

        result = EarlyWarningRunResult(dry_run=dry_run)
        run_id: str | None = None
        previous_reporter = self.reporter
        if self.progress_tracker is not None:
            run_id = self.progress_tracker.start_run(
                pipeline_kind=PipelineKind.EARLY_WARNING,
                details={"dry_run": dry_run},
            )
            self.reporter = self.progress_tracker.reporter(run_id)
        self._active_run_id = run_id

        try:
            if self.search_client is None:
                raise RuntimeError("early warning is enabled but Brave Search is unavailable")

            self._log(PipelineStage.EARLY_WARNING, "Starting early-warning discovery")
            candidates = await self._search_and_queue(result)
            if result.queries_searched > 0 and result.search_results == 0:
                self._warn(
                    WarningCategory.EARLY_WARNING_SEARCH_FAILED,
                    "Early-warning search returned no results for this run",
                )
            if dry_run:
                self._log(
                    PipelineStage.EARLY_WARNING,
                    "Completed early-warning discovery dry run",
                    details=_safe_metrics(result),
                )
                if self.progress_tracker is not None and run_id is not None:
                    self.progress_tracker.complete_run(
                        run_id=run_id,
                        summary=_safe_metrics(result),
                    )
                return result

            accepted = await self._review_candidates(candidates, result)
            records = await self._scrape(accepted, result)
            records = await self._expand_listing_pages(records, result)

            for candidate, record in records:
                try:
                    processed_incident = self._already_processed(record)
                    if processed_incident is not None:
                        self.candidate_store.upsert_candidate(
                            candidate.mark_status(
                                CandidateStatus.CONVERTED,
                                content_hash=str(record.payload.get("content_hash") or ""),
                                final_url=str(
                                    record.payload.get("final_url") or candidate.canonical_url
                                ),
                                linked_incident_id=processed_incident.incident_id,
                            )
                        )
                        continue
                    source_kind, trust_tier = self._source_profile(candidate.canonical_url)
                    before = self.incident_service.store.count_incidents()
                    incident_create = await self.processing_service.process_record(
                        record,
                        source_kind=source_kind,
                        trust_tier=trust_tier,
                    )
                    result.records_processed += 1
                    if incident_create is None:
                        result.irrelevant_pages += 1
                        self.candidate_store.upsert_candidate(
                            candidate.mark_status(CandidateStatus.CLASSIFIED).model_copy(
                                update={
                                    "decision": CandidateDecision.REJECT,
                                    "reasons": [
                                        *candidate.reasons,
                                        "page classified as irrelevant",
                                    ],
                                }
                            )
                        )
                        continue
                    target_country = self._target_country_for_incident(incident_create)
                    if target_country is None:
                        result.irrelevant_pages += 1
                        self.candidate_store.upsert_candidate(
                            candidate.mark_status(CandidateStatus.CLASSIFIED).model_copy(
                                update={
                                    "decision": CandidateDecision.REJECT,
                                    "reasons": [
                                        *candidate.reasons,
                                        "incident is outside configured target countries",
                                    ],
                                }
                            )
                        )
                        continue
                    incident_create = incident_create.model_copy(
                        update={"country": target_country}
                    )
                    incident = self.incident_service.save_incident(incident_create)
                    self.candidate_store.upsert_candidate(
                        candidate.mark_status(
                            CandidateStatus.CONVERTED,
                            content_hash=str(record.payload.get("content_hash") or ""),
                            final_url=str(
                                record.payload.get("final_url") or candidate.canonical_url
                            ),
                            linked_incident_id=incident.incident_id,
                        )
                    )
                    result.incidents_saved += 1
                    if self.incident_service.store.count_incidents() > before:
                        result.new_incidents += 1
                    self._log(
                        PipelineStage.EARLY_WARNING_DB,
                        "Early-warning incident persisted",
                        source=incident.primary_source_domain,
                        details={"incident_id": incident.incident_id},
                    )
                    if self.verification_service is not None:
                        try:
                            verification = self.verification_service.verify_incident(
                                incident.incident_id
                            )
                            if verification is not None and verification.confirmed:
                                result.officially_confirmed += 1
                        except Exception as exc:  # noqa: BLE001 - keep incident even if verify fails
                            self._warn(
                                WarningCategory.EARLY_WARNING_RECORD_SKIPPED,
                                "Early-warning official verification failed",
                                source=incident.primary_source_domain,
                                error=exc,
                            )
                    if self.broadcaster is not None:
                        self.broadcaster.notify(1)
                except Exception as exc:  # noqa: BLE001 - isolate individual discovered pages
                    result.failures[candidate.canonical_url] = str(exc)
                    self.candidate_store.upsert_candidate(
                        candidate.mark_status(
                            CandidateStatus.RETRYABLE,
                            error=str(exc),
                            next_retry_at=self._next_retry_at(),
                            increment_attempt=True,
                        )
                    )
                    self._warn(
                        WarningCategory.EARLY_WARNING_RECORD_SKIPPED,
                        "Early-warning page skipped during AI processing",
                        source=urlsplit(candidate.canonical_url).hostname,
                        error=exc,
                    )

            self._log(
                PipelineStage.EARLY_WARNING,
                "Completed early-warning discovery",
                details=_safe_metrics(result),
            )
            if self.progress_tracker is not None and run_id is not None:
                self.progress_tracker.complete_run(
                    run_id=run_id,
                    summary=_safe_metrics(result),
                )
            return result
        except Exception as exc:
            if self.progress_tracker is not None and run_id is not None:
                self.progress_tracker.fail_run(run_id=run_id, error=str(exc))
            self._warn(
                WarningCategory.EARLY_WARNING_PIPELINE_FAILED,
                "Early-warning pipeline run failed",
                error=exc,
            )
            raise
        finally:
            self.reporter = previous_reporter
            self._active_run_id = None

    run_pipeline = run  # Alias matching the official PipelineService naming.

    async def _search_and_queue(
        self,
        result: EarlyWarningRunResult,
    ) -> list[DiscoveryCandidate]:
        """Search Brave and upsert borderline candidates up to the budget.

        Args:
            result: Mutable run metrics accumulator.

        Returns:
            Discovery candidates discovered during this search pass.
        """
        states = self.candidate_store.list_query_states()
        rotation = sum(state.search_count for state in states) // max(
            1,
            self.config.budgets.queries_per_run,
        )
        queries = QueryGenerator(self.config).generate(rotation=rotation)
        discovered: dict[str, DiscoveryCandidate] = {}
        remaining = self.config.budgets.candidates_per_run

        for query in queries:
            if remaining <= 0:
                break
            state = self.candidate_store.get_query_state(query.query_id) or EarlyWarningQueryState(
                query=query
            )
            offset = 0
            searched = False
            for _page in range(self.config.budgets.max_pages_per_query):
                if remaining <= 0:
                    break
                try:
                    response = await self.search_client.search(
                        query,
                        count=min(self.config.budgets.results_per_query, remaining),
                        offset=offset,
                    )
                except Exception as exc:  # noqa: BLE001 - continue other queries
                    result.failures[f"query:{query.query_id}"] = str(exc)
                    self._warn(
                        WarningCategory.EARLY_WARNING_SEARCH_FAILED,
                        f'Early-warning search query "{query.query_id}" failed',
                        source=query.country,
                        error=exc,
                    )
                    break
                searched = True
                result.queries_searched += 1
                result.search_results += len(response.candidates)
                useful_this_page = 0
                for search_candidate in response.candidates:
                    # Every search result must be reviewed by the LLM before it can
                    # be fetched. Do not use lexical, URL, or domain heuristics to
                    # pre-accept or reject pages: they routinely misclassify
                    # non-food recalls.
                    candidate = DiscoveryCandidate.from_search(
                        search_candidate,
                        decision=CandidateDecision.BORDERLINE,
                        confidence=0.5,
                        reasons=["awaiting LLM food-safety relevance review"],
                    )
                    candidate = self.candidate_store.upsert_candidate(
                        candidate
                    )
                    discovered[candidate.candidate_id] = candidate
                    if self._eligible_for_processing(candidate):
                        result.candidates_borderline += 1
                        useful_this_page += 1
                remaining -= useful_this_page
                if (
                    not response.more_results_available
                    or response.offset >= 9
                    or not response.candidates
                ):
                    break
                offset = response.offset + 1
            if searched:
                self.candidate_store.upsert_query_state(
                    state.record_search(
                        searched_at=datetime.now(timezone.utc),
                        next_offset=0,
                    )
                )
        return list(discovered.values())

    async def _review_candidates(
        self,
        candidates: list[DiscoveryCandidate],
        result: EarlyWarningRunResult,
    ) -> list[DiscoveryCandidate]:
        """LLM-review new and previously eligible stored candidates.

        Args:
            candidates: Candidates discovered in the current search pass.
            result: Mutable run metrics accumulator.

        Returns:
            Accepted candidates ready for scraping.
        """
        accepted: list[DiscoveryCandidate] = []
        seen_ids: set[str] = set()
        for candidate in candidates:
            reviewed = await self._review_one_candidate(candidate, result)
            if reviewed is None or reviewed.candidate_id in seen_ids:
                continue
            seen_ids.add(reviewed.candidate_id)
            accepted.append(reviewed)

        for stored in self.candidate_store.list_candidates():
            if stored.candidate_id in seen_ids:
                continue
            if not self._eligible_for_processing(stored):
                continue
            seen_ids.add(stored.candidate_id)
            reviewed = await self._review_one_candidate(stored, result)
            if reviewed is not None:
                accepted.append(reviewed)
        return accepted

    async def _review_one_candidate(
        self,
        candidate: DiscoveryCandidate,
        result: EarlyWarningRunResult,
    ) -> DiscoveryCandidate | None:
        """Classify one candidate's metadata and persist the decision.

        Args:
            candidate: Candidate to review.
            result: Mutable run metrics accumulator.

        Returns:
            Accepted candidate, or None when rejected/ineligible.
        """
        if not self._eligible_for_processing(candidate):
            return None
        try:
            # Metadata classification calls the synchronous Ollama client. Every
            # eligible search result (including candidates accepted by older runs)
            # is reviewed before fetch.
            relevance = await asyncio.to_thread(
                self.processing_service.classify_borderline,
                candidate,
            )
            decision = (
                CandidateDecision.ACCEPT if relevance.relevant else CandidateDecision.REJECT
            )
            reviewed = candidate.model_copy(
                update={
                    "decision": decision,
                    "processing_status": (
                        CandidateStatus.ACCEPTED
                        if decision == CandidateDecision.ACCEPT
                        else CandidateStatus.REJECTED
                    ),
                    "reasons": [*candidate.reasons, f"LLM review: {relevance.reason}"],
                }
            )
            reviewed = self.candidate_store.upsert_candidate(reviewed)
            if decision == CandidateDecision.ACCEPT:
                result.candidates_accepted += 1
                return reviewed
            result.candidates_rejected += 1
            return None
        except Exception as exc:  # noqa: BLE001 - conservative rejection on metadata failure
            result.failures[candidate.canonical_url] = str(exc)
            self.candidate_store.upsert_candidate(
                candidate.model_copy(
                    update={
                        "decision": CandidateDecision.REJECT,
                        "processing_status": CandidateStatus.REJECTED,
                        "reasons": [
                            *candidate.reasons,
                            f"LLM review failed: {exc}",
                        ],
                    }
                )
            )
            result.candidates_rejected += 1
            self._warn(
                WarningCategory.EARLY_WARNING_RECORD_SKIPPED,
                "Borderline early-warning candidate could not be classified",
                source=urlsplit(candidate.canonical_url).hostname,
                error=exc,
            )
            return None

    async def _scrape(
        self,
        candidates: list[DiscoveryCandidate],
        result: EarlyWarningRunResult,
    ) -> list[tuple[DiscoveryCandidate, ScrapedRecallRecord]]:
        """Fetch accepted candidate URLs concurrently under a semaphore.

        Args:
            candidates: Accepted candidates to ingest.
            result: Mutable run metrics accumulator.

        Returns:
            Successfully scraped ``(candidate, record)`` pairs.
        """
        semaphore = asyncio.Semaphore(self.config.crawl.concurrency)
        timeout = httpx.Timeout(self.config.crawl.timeout_seconds)
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
        ) as client:
            async def scrape_one(
                candidate: DiscoveryCandidate,
            ) -> tuple[DiscoveryCandidate, ScrapedRecallRecord] | None:
                """Ingest one candidate URL and update its status.

                Args:
                    candidate: Candidate whose URL should be fetched.

                Returns:
                    ``(candidate, record)`` on success, otherwise None.
                """
                async with semaphore:
                    try:
                        record = await self.ingest(
                            candidate.canonical_url,
                            client=client,
                            candidate=candidate,
                            minimum_text_characters=self.config.crawl.minimum_text_characters,
                            timeout_seconds=self.config.crawl.timeout_seconds,
                        )
                        candidate = self.candidate_store.upsert_candidate(
                            candidate.mark_status(
                                CandidateStatus.ACCEPTED,
                                content_hash=str(record.payload.get("content_hash") or ""),
                                final_url=str(
                                    record.payload.get("final_url") or candidate.canonical_url
                                ),
                                increment_attempt=True,
                            )
                        )
                        result.pages_scraped += 1
                        return candidate, record
                    except UnsupportedContentError as exc:
                        result.failures[candidate.canonical_url] = str(exc)
                        self.candidate_store.upsert_candidate(
                            candidate.mark_status(
                                CandidateStatus.UNSUPPORTED_CONTENT,
                                error=str(exc),
                                increment_attempt=True,
                            )
                        )
                        self._warn(
                            WarningCategory.EARLY_WARNING_FETCH_FAILED,
                            "Early-warning page has unsupported content type",
                            source=urlsplit(candidate.canonical_url).hostname,
                            error=exc,
                        )
                        return None
                    except Exception as exc:  # noqa: BLE001 - isolate crawl failures
                        result.failures[candidate.canonical_url] = str(exc)
                        next_attempt = candidate.attempt_count + 1
                        terminal = next_attempt >= self.config.crawl.max_attempts
                        self.candidate_store.upsert_candidate(
                            candidate.mark_status(
                                CandidateStatus.FETCH_FAILED
                                if terminal
                                else CandidateStatus.RETRYABLE,
                                error=str(exc),
                                next_retry_at=None if terminal else self._next_retry_at(),
                                increment_attempt=True,
                            )
                        )
                        self._warn(
                            WarningCategory.EARLY_WARNING_FETCH_FAILED,
                            "Early-warning page fetch failed",
                            source=urlsplit(candidate.canonical_url).hostname,
                            error=exc,
                        )
                        return None

            scraped = await asyncio.gather(*(scrape_one(candidate) for candidate in candidates))
        return [item for item in scraped if item is not None]

    async def _expand_listing_pages(
        self,
        records: list[tuple[DiscoveryCandidate, ScrapedRecallRecord]],
        result: EarlyWarningRunResult,
    ) -> list[tuple[DiscoveryCandidate, ScrapedRecallRecord]]:
        """Replace listing/index pages with a bounded set of their detail pages.

        Args:
            records: Scraped candidate/record pairs from the first pass.
            result: Mutable run metrics accumulator.

        Returns:
            Detail-page records (listing pages themselves are rejected).
        """
        detail_records: list[tuple[DiscoveryCandidate, ScrapedRecallRecord]] = []
        children: list[DiscoveryCandidate] = []
        seen_urls: set[str] = set()
        for candidate, record in records:
            links = _listing_detail_links(record)
            if not links:
                detail_records.append((candidate, record))
                continue
            result.irrelevant_pages += 1
            self.candidate_store.upsert_candidate(
                candidate.mark_status(CandidateStatus.CLASSIFIED).model_copy(
                    update={
                        "decision": CandidateDecision.REJECT,
                        "reasons": [
                            *candidate.reasons,
                            f"listing page expanded to {len(links)} detail links",
                        ],
                    }
                )
            )
            now = datetime.now(timezone.utc)
            for link in links[:MAX_LISTING_DETAIL_LINKS]:
                url = str(link.get("url") or "").strip()
                if not url or url == candidate.canonical_url or url in seen_urls:
                    continue
                seen_urls.add(url)
                child = DiscoveryCandidate(
                    canonical_url=url,
                    title=str(link.get("title") or "Recall detail").strip()
                    or "Recall detail",
                    description=f"Discovered from listing {candidate.canonical_url}",
                    country=candidate.country,
                    language=candidate.language,
                    decision=CandidateDecision.ACCEPT,
                    confidence=candidate.confidence,
                    reasons=[
                        *candidate.reasons,
                        f"detail link discovered from {candidate.canonical_url}",
                    ],
                    query_ids=list(candidate.query_ids),
                    first_seen_at=now,
                    last_seen_at=now,
                    processing_status=CandidateStatus.ACCEPTED,
                )
                stored = self.candidate_store.upsert_candidate(child)
                if self._eligible_for_processing(stored):
                    children.append(stored)
        if children:
            detail_records.extend(await self._scrape(children, result))
        return detail_records

    def _target_country_for_incident(
        self,
        incident: Any,
    ) -> str | None:
        """Map an incident onto a configured target country name.

        Args:
            incident: Incident create payload with country/regions/URL.

        Returns:
            Canonical configured country name, or None when out of scope.
        """
        enabled = [country for country in self.config.countries if country.enabled]
        reported_places = [incident.country, *incident.affected_regions]
        for country in enabled:
            aliases = [country.code, country.name, *country.aliases]
            if any(
                _place_matches_alias(place, alias)
                for place in reported_places
                for alias in aliases
            ):
                return country.name
        hostname = (urlsplit(incident.primary_source_url).hostname or "").lower()
        for country in enabled:
            if any(
                hostname == domain or hostname.endswith(f".{domain}")
                for domain in country.domains
            ):
                return country.name
        return None

    def _source_profile(self, url: str) -> tuple[SourceKind, TrustTier]:
        """Resolve configured domain source kind and trust for a URL.

        Args:
            url: Page URL whose hostname is matched against domain profiles.

        Returns:
            ``(source_kind, trust_tier)``, defaulting to UNKNOWN/UNKNOWN.
        """
        hostname = (urlsplit(url).hostname or "").lower()
        matches = [
            (domain, profile)
            for domain, profile in self.config.domains.profiles.items()
            if hostname == domain or hostname.endswith(f".{domain}")
        ]
        if matches:
            _domain, profile = max(matches, key=lambda item: len(item[0]))
            return SourceKind(profile.source_kind), TrustTier(profile.trust_tier)
        return SourceKind.UNKNOWN, TrustTier.UNKNOWN

    def _already_processed(self, record: ScrapedRecallRecord) -> EarlyWarningIncident | None:
        """Find an existing incident with the same content hash.

        Args:
            record: Scraped record whose content_hash is checked.

        Returns:
            Matching incident, or None when unseen.
        """
        content_hash = str(record.payload.get("content_hash") or "").strip().lower()
        if not content_hash:
            return None
        return next(
            (
                incident
                for incident in self.incident_service.store.list_incidents()
                for evidence in incident.evidence
                if evidence.content_hash.strip()
                and evidence.content_hash.strip().lower() == content_hash
            ),
            None,
        )

    def _eligible_for_processing(self, candidate: DiscoveryCandidate) -> bool:
        """Return whether a candidate may still be reviewed or scraped.

        Args:
            candidate: Candidate whose status and retry schedule are checked.

        Returns:
            True when the candidate is eligible for further processing.
        """
        if candidate.processing_status in {
            CandidateStatus.CONVERTED,
            CandidateStatus.CLASSIFIED,
            CandidateStatus.UNSUPPORTED_CONTENT,
            CandidateStatus.REJECTED,
        }:
            return False
        if (
            candidate.processing_status == CandidateStatus.FETCH_FAILED
            and candidate.attempt_count >= self.config.crawl.max_attempts
        ):
            return False
        now = datetime.now(timezone.utc)
        return candidate.next_retry_at is None or candidate.next_retry_at <= now

    def _next_retry_at(self) -> datetime:
        """Compute the next retry timestamp from crawl config.

        Returns:
            UTC datetime when a failed candidate may be retried.
        """
        return datetime.now(timezone.utc) + timedelta(
            minutes=self.config.crawl.retry_delay_minutes
        )

    def _warn(
        self,
        category: WarningCategory,
        message: str,
        *,
        source: str | None = None,
        error: BaseException | str | None = None,
    ) -> None:
        """Log and optionally persist an operational warning.

        Args:
            category: Warning category.
            message: Base warning message.
            source: Optional source hostname or label.
            error: Optional exception or detail appended to the message.
        """
        detail = str(error).strip() if error is not None else ""
        full_message = f"{message}: {detail}" if detail else message
        LOGGER.warning("%s%s", full_message, f" ({source})" if source else "")
        if self.warnings_service is not None:
            self.warnings_service.emit(
                category=category,
                message=full_message,
                source=source,
                run_id=self._active_run_id,
            )

    def _log(
        self,
        stage: PipelineStage,
        message: str,
        *,
        source: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Emit an info log and optional progress-reporter event.

        Args:
            stage: Pipeline stage for the event.
            message: Human-readable progress message.
            source: Optional source label.
            details: Optional structured metrics/details.
        """
        LOGGER.info(
            "%s%s%s",
            message,
            f" ({source})" if source else "",
            f" metrics={details}" if details else "",
        )
        if self.reporter is not None:
            self.reporter.log(stage=stage, message=message, source=source, details=details)


def _safe_metrics(result: EarlyWarningRunResult) -> dict[str, int]:
    """Extract JSON-safe integer metrics from a run result.

    Args:
        result: Completed or in-progress run result.

    Returns:
        Dict of integer metrics suitable for log event details.
    """
    return {
        "queries_searched": result.queries_searched,
        "search_results": result.search_results,
        "candidates_accepted": result.candidates_accepted,
        "candidates_borderline": result.candidates_borderline,
        "candidates_rejected": result.candidates_rejected,
        "pages_scraped": result.pages_scraped,
        "records_processed": result.records_processed,
        "irrelevant_pages": result.irrelevant_pages,
        "incidents_saved": result.incidents_saved,
        "new_incidents": result.new_incidents,
        "officially_confirmed": result.officially_confirmed,
        "failure_count": len(result.failures),
    }


def _listing_detail_links(record: ScrapedRecallRecord) -> list[dict[str, str]]:
    """Detect listing pages and return their detail-link payloads.

    Args:
        record: Scraped page that may be a listing/index.

    Returns:
        Detail link dicts when the page looks like a listing; otherwise [].
    """
    raw_links = record.payload.get("detail_links")
    if not isinstance(raw_links, list):
        return []
    links = [item for item in raw_links if isinstance(item, dict) and item.get("url")]
    if len(links) < 3:
        return []
    title = str(record.payload.get("title") or "").casefold()
    path = urlsplit(str(record.payload.get("canonical_url") or "")).path.casefold()
    generic_listing = any(signal in f"{title} {path}" for signal in _LISTING_TITLE_SIGNALS)
    return links if generic_listing or len(links) >= 5 else []


def _normalize_place(value: object) -> str:
    """Normalize a place label for alias comparison.

    Args:
        value: Raw country or region string.

    Returns:
        ASCII, lowercased, punctuation-stripped place token string.
    """
    text = unicodedata.normalize("NFKD", str(value or ""))
    ascii_text = "".join(character for character in text if not unicodedata.combining(character))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", ascii_text.casefold()).split())


def _place_matches_alias(place: object, alias: object) -> bool:
    """Return whether a reported place matches a configured country alias.

    Args:
        place: Reported country or region value.
        alias: Configured country code, name, or alias.

    Returns:
        True on exact match, or word-boundary match for aliases length >= 4.
    """
    normalized_place = _normalize_place(place)
    normalized_alias = _normalize_place(alias)
    if not normalized_place or not normalized_alias:
        return False
    if normalized_place == normalized_alias:
        return True
    # Avoid accidental substring matches for short codes such as DE/FR/GB.
    return len(normalized_alias) >= 4 and re.search(
        rf"\b{re.escape(normalized_alias)}\b", normalized_place
    ) is not None
