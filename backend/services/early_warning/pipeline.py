from __future__ import annotations

import asyncio
import logging
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
from services.early_warning.candidate_filter import CandidateFilter
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

LOGGER = logging.getLogger(__name__)
IngestCallable = Callable[..., Awaitable[ScrapedRecallRecord]]


@dataclass
class EarlyWarningRunResult:
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

    async def run(self, *, dry_run: bool = False) -> EarlyWarningRunResult:
        if self.run_lock is None:
            return await self._run(dry_run=dry_run)
        if self.run_lock.locked():
            LOGGER.warning("Skipping overlapping early-warning pipeline run")
            return EarlyWarningRunResult(
                dry_run=dry_run,
                skipped_due_to_overlap=True,
            )
        async with self.run_lock:
            return await self._run(dry_run=dry_run)

    async def _run(self, *, dry_run: bool = False) -> EarlyWarningRunResult:
        if not self.config.enabled:
            return EarlyWarningRunResult(dry_run=dry_run)
        if self.search_client is None:
            raise RuntimeError("early warning is enabled but Brave Search is unavailable")

        result = EarlyWarningRunResult(dry_run=dry_run)
        run_id: str | None = None
        previous_reporter = self.reporter
        if self.progress_tracker is not None:
            run_id = self.progress_tracker.start_run(
                pipeline_kind=PipelineKind.EARLY_WARNING,
                details={"dry_run": dry_run},
            )
            self.reporter = self.progress_tracker.reporter(run_id)

        try:
            self._log(PipelineStage.EARLY_WARNING, "Starting early-warning discovery")
            candidates = await self._search_and_filter(result)
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

            accepted = await self._review_borderline(candidates, result)
            records = await self._scrape(accepted, result)

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
                        verification = self.verification_service.verify_incident(
                            incident.incident_id
                        )
                        if verification is not None and verification.confirmed:
                            result.officially_confirmed += 1
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
            )
            raise
        finally:
            self.reporter = previous_reporter

    run_pipeline = run

    async def _search_and_filter(
        self,
        result: EarlyWarningRunResult,
    ) -> list[DiscoveryCandidate]:
        states = self.candidate_store.list_query_states()
        rotation = sum(state.search_count for state in states) // max(
            1,
            self.config.budgets.queries_per_run,
        )
        queries = QueryGenerator(self.config).generate(rotation=rotation)
        candidate_filter = CandidateFilter(self.config)
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
                        "An early-warning search query failed",
                    )
                    break
                searched = True
                result.queries_searched += 1
                result.search_results += len(response.candidates)
                for filtered in candidate_filter.filter(response.candidates):
                    candidate = self.candidate_store.upsert_candidate(
                        filtered.to_discovery_candidate()
                    )
                    discovered[candidate.candidate_id] = candidate
                    if candidate.decision == CandidateDecision.ACCEPT:
                        result.candidates_accepted += 1
                    elif candidate.decision == CandidateDecision.BORDERLINE:
                        result.candidates_borderline += 1
                    else:
                        result.candidates_rejected += 1
                remaining -= len(response.candidates)
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

    async def _review_borderline(
        self,
        candidates: list[DiscoveryCandidate],
        result: EarlyWarningRunResult,
    ) -> list[DiscoveryCandidate]:
        accepted: list[DiscoveryCandidate] = []
        for candidate in candidates:
            if not self._eligible_for_processing(candidate):
                continue
            if candidate.decision == CandidateDecision.ACCEPT:
                accepted.append(candidate)
                continue
            if candidate.decision != CandidateDecision.BORDERLINE:
                continue
            try:
                relevance = self.processing_service.classify_borderline(candidate)
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
                    accepted.append(reviewed)
                    result.candidates_accepted += 1
                else:
                    result.candidates_rejected += 1
            except Exception:  # noqa: BLE001 - conservative rejection on metadata failure
                self._warn(
                    WarningCategory.EARLY_WARNING_RECORD_SKIPPED,
                    "Borderline early-warning candidate could not be classified",
                    source=urlsplit(candidate.canonical_url).hostname,
                )
        return accepted

    async def _scrape(
        self,
        candidates: list[DiscoveryCandidate],
        result: EarlyWarningRunResult,
    ) -> list[tuple[DiscoveryCandidate, ScrapedRecallRecord]]:
        semaphore = asyncio.Semaphore(self.config.crawl.concurrency)
        timeout = httpx.Timeout(self.config.crawl.timeout_seconds)
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
        ) as client:
            async def scrape_one(
                candidate: DiscoveryCandidate,
            ) -> tuple[DiscoveryCandidate, ScrapedRecallRecord] | None:
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
                        )
                        return None

            scraped = await asyncio.gather(*(scrape_one(candidate) for candidate in candidates))
        return [item for item in scraped if item is not None]

    def _source_profile(self, url: str) -> tuple[SourceKind, TrustTier]:
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
        if candidate.processing_status == CandidateStatus.CONVERTED:
            return False
        if (
            candidate.processing_status == CandidateStatus.FETCH_FAILED
            and candidate.attempt_count >= self.config.crawl.max_attempts
        ):
            return False
        if candidate.processing_status == CandidateStatus.UNSUPPORTED_CONTENT:
            return False
        now = datetime.now(timezone.utc)
        return candidate.next_retry_at is None or candidate.next_retry_at <= now

    def _next_retry_at(self) -> datetime:
        return datetime.now(timezone.utc) + timedelta(
            minutes=self.config.crawl.retry_delay_minutes
        )

    def _warn(
        self,
        category: WarningCategory,
        message: str,
        *,
        source: str | None = None,
    ) -> None:
        LOGGER.warning("%s%s", message, f" ({source})" if source else "")
        if self.warnings_service is not None:
            self.warnings_service.emit(category=category, message=message, source=source)

    def _log(
        self,
        stage: PipelineStage,
        message: str,
        *,
        source: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        LOGGER.info(
            "%s%s%s",
            message,
            f" ({source})" if source else "",
            f" metrics={details}" if details else "",
        )
        if self.reporter is not None:
            self.reporter.log(stage=stage, message=message, source=source, details=details)


def _safe_metrics(result: EarlyWarningRunResult) -> dict[str, int]:
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
