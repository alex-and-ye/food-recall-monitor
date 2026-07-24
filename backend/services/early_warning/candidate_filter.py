from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import unquote, urlsplit

from pydantic import BaseModel

from config.early_warning import EarlyWarningConfig
from models.discovery_candidate import CandidateDecision, DiscoveryCandidate
from models.search_candidate import SearchCandidate


class CandidateFilterResult(BaseModel):
    decision: CandidateDecision
    confidence: float
    reasons: list[str]
    search_candidate: SearchCandidate

    def to_discovery_candidate(
        self,
        *,
        seen_at: datetime | None = None,
    ) -> DiscoveryCandidate:
        return DiscoveryCandidate.from_search(
            self.search_candidate,
            decision=self.decision,
            confidence=self.confidence,
            reasons=self.reasons,
            seen_at=seen_at,
        )


class CandidateFilter:
    """Deterministic lexical/domain filter; LLM review belongs downstream."""

    def __init__(self, config: EarlyWarningConfig) -> None:
        self._config = config
        self._countries = {
            country.code: country for country in config.countries if country.enabled
        }

    def evaluate(self, candidate: SearchCandidate) -> CandidateFilterResult:
        hostname = (urlsplit(candidate.url).hostname or "").lower().rstrip(".")
        path_text = _normalize_match_text(unquote(urlsplit(candidate.url).path))
        searchable_text = _normalize_match_text(
            " ".join(
                (
                    candidate.title,
                    candidate.description,
                    unquote(urlsplit(candidate.url).path),
                )
            )
        )
        reasons: list[str] = []

        country = self._countries.get(candidate.country.upper())
        if country is None:
            return self._result(
                candidate,
                CandidateDecision.REJECT,
                0.0,
                [f"country is not enabled: {candidate.country}"],
            )
        excluded_domain = _matching_domain(hostname, self._config.domains.excluded)
        if excluded_domain is not None:
            return self._result(
                candidate,
                CandidateDecision.REJECT,
                0.0,
                [f"excluded domain: {excluded_domain}"],
            )
        exclusion_term = _matching_term(searchable_text, self._config.terms.exclusions)
        if exclusion_term is not None:
            return self._result(
                candidate,
                CandidateDecision.REJECT,
                0.0,
                [f"excluded topic term: {exclusion_term}"],
            )

        language_terms = self._config.languages.get(candidate.language.lower())
        recall_match = (
            _matching_term(searchable_text, language_terms.recall)
            if language_terms is not None
            else None
        )
        food_match = (
            _matching_term(searchable_text, language_terms.food)
            if language_terms is not None
            else None
        )
        trusted_match = _matching_domain(hostname, self._config.domains.trusted)
        country_match = _matching_domain(hostname, country.domains)
        path_match = _matching_term(path_text, self._config.terms.path_signals)

        weights = self._config.confidence
        score = 0.0
        if recall_match is not None:
            score += weights.recall_term
            reasons.append(f"recall term: {recall_match}")
        else:
            reasons.append("no recall term")
        if food_match is not None:
            score += weights.food_term
            reasons.append(f"food term: {food_match}")
        else:
            reasons.append("no food term")
        if trusted_match is not None:
            score += weights.trusted_domain
            reasons.append(f"trusted domain: {trusted_match}")
        if country_match is not None:
            score += weights.country_domain
            reasons.append(f"country domain: {country_match}")
        if path_match is not None:
            score += weights.path_signal
            reasons.append(f"path signal: {path_match}")
        if candidate.description.strip():
            score += weights.description
            reasons.append("search description present")

        confidence = round(min(1.0, max(0.0, score / weights.total)), 6)
        if confidence >= self._config.thresholds.accept:
            decision = CandidateDecision.ACCEPT
        elif confidence <= self._config.thresholds.reject:
            decision = CandidateDecision.REJECT
        else:
            decision = CandidateDecision.BORDERLINE
        return self._result(candidate, decision, confidence, reasons)

    def filter(self, candidates: list[SearchCandidate]) -> list[CandidateFilterResult]:
        return [self.evaluate(candidate) for candidate in candidates]

    @staticmethod
    def _result(
        candidate: SearchCandidate,
        decision: CandidateDecision,
        confidence: float,
        reasons: list[str],
    ) -> CandidateFilterResult:
        return CandidateFilterResult(
            decision=decision,
            confidence=confidence,
            reasons=reasons,
            search_candidate=candidate,
        )


def filter_candidate(
    candidate: SearchCandidate,
    config: EarlyWarningConfig,
) -> CandidateFilterResult:
    return CandidateFilter(config).evaluate(candidate)


def _matching_domain(hostname: str, domains: list[str]) -> str | None:
    for domain in domains:
        if hostname == domain or hostname.endswith(f".{domain}"):
            return domain
    return None


def _matching_term(text: str, terms: list[str]) -> str | None:
    normalized_text = _normalize_match_text(text)
    for term in terms:
        if _normalize_match_text(term) in normalized_text:
            return term
    return None


def _normalize_match_text(value: str) -> str:
    return re.sub(r"[-_/]+", " ", value).casefold()
