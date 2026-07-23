from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date, datetime, timezone
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field

from agents.fetchers.scraper_ingestion import to_translator_envelope
from agents.llm import AgentOutputError, chat_json, chat_text
from agents.prompts import TRANSLATION_SYSTEM_PROMPT
from agents.validators import AgentValidationError, validate_translated_structure
from config.agents import CLASSIFICATION_MODEL, STRUCTURING_MODEL, TRANSLATION_MODEL
from models.discovery_candidate import DiscoveryCandidate
from models.early_warning_incident import (
    EarlyWarningIncidentCreate,
    IncidentEvidence,
    IncidentType,
    SourceKind,
    TrustTier,
)
from models.scraped_record import ScrapedRecallRecord

ContentTaxonomy = Literal[
    "official_recall",
    "potential_recall",
    "foodborne_outbreak",
    "investigation",
    "company_withdrawal",
    "public_health_warning",
    "food_safety_advisory",
    "irrelevant",
]

TAXONOMY_PROMPT = """Classify the supplied page using exactly one content_type:
official_recall, potential_recall, foodborne_outbreak, investigation,
company_withdrawal, public_health_warning, food_safety_advisory, irrelevant.
Use irrelevant for historical summaries, generic food advice, unrelated products,
or pages without a current concrete food-safety event. Do not infer a recall merely
from cautious or speculative wording. Return JSON with content_type and reason."""

BORDERLINE_PROMPT = """Decide whether this search-result metadata is sufficiently
likely to describe a current concrete food-safety incident to justify fetching.
Accept recalls, withdrawals, outbreaks, illness clusters, contamination reports,
investigations, public-health warnings, and food-safety advisories. Reject generic
advice, recipes, historical pages, and non-food product recalls. Return JSON:
{"relevant": true|false, "reason": "..."}."""

SUMMARY_PROMPT = """Write a concise factual summary of the supplied food-safety page.
Preserve uncertainty and attribution. Never upgrade an investigation, allegation,
or potential issue into a confirmed recall. Include consumer guidance only when the
source explicitly provides it. Return plain text only."""

STRUCTURING_PROMPT = """Extract one current food-safety incident from the supplied
translated page and summary. Return one JSON object with these keys:
product_name, company_name, product_category, hazard_type, incident_reason,
consumer_guidance, country, affected_regions (array), publication_date (YYYY-MM-DD
or null), publisher, original_language, extraction_completeness (0..1).
Use empty strings/arrays for facts not supported by the source. Do not invent facts."""


class TaxonomyResult(BaseModel):
    content_type: ContentTaxonomy
    reason: str = ""


class BorderlineRelevance(BaseModel):
    relevant: bool
    reason: str = ""


class IncidentExtraction(BaseModel):
    product_name: str = ""
    company_name: str = ""
    product_category: str = ""
    hazard_type: str = ""
    incident_reason: str = ""
    consumer_guidance: str = ""
    country: str = ""
    affected_regions: list[str] = Field(default_factory=list)
    publication_date: date | None = None
    publisher: str = ""
    original_language: str = ""
    extraction_completeness: float = Field(default=0.0, ge=0.0, le=1.0)


class EarlyWarningProcessingService:
    def __init__(
        self,
        *,
        json_chat: Callable[..., dict[str, Any]] = chat_json,
        text_chat: Callable[..., str] = chat_text,
    ) -> None:
        self._json_chat = json_chat
        self._text_chat = text_chat

    def classify_borderline(self, candidate: DiscoveryCandidate) -> BorderlineRelevance:
        payload = {
            "title": candidate.title,
            "description": candidate.description,
            "url": candidate.canonical_url,
            "country": candidate.country,
            "language": candidate.language,
        }
        response = self._json_chat(
            system_prompt=BORDERLINE_PROMPT,
            user_prompt=json.dumps(payload, ensure_ascii=False),
            model=CLASSIFICATION_MODEL,
        )
        return BorderlineRelevance.model_validate(response)

    async def process_record(
        self,
        record: ScrapedRecallRecord,
        *,
        source_kind: SourceKind = SourceKind.UNKNOWN,
        trust_tier: TrustTier = TrustTier.UNKNOWN,
    ) -> EarlyWarningIncidentCreate | None:
        translated = self._translate(record)
        taxonomy = TaxonomyResult.model_validate(
            self._json_chat(
                system_prompt=TAXONOMY_PROMPT,
                user_prompt=json.dumps(translated, ensure_ascii=False),
                model=CLASSIFICATION_MODEL,
            )
        )
        if taxonomy.content_type == "irrelevant":
            return None

        summary = self._text_chat(
            system_prompt=SUMMARY_PROMPT,
            user_prompt=json.dumps(translated, ensure_ascii=False),
        ).strip()
        if not summary:
            raise AgentOutputError("early-warning summary was empty")
        extraction = self._extract(translated, summary)
        return _to_incident(
            record,
            taxonomy=taxonomy,
            extraction=extraction,
            summary=summary,
            source_kind=source_kind,
            trust_tier=trust_tier,
        )

    async def ainvoke(self, state: dict[str, Any]) -> dict[str, Any]:
        record = state.get("record")
        if not isinstance(record, ScrapedRecallRecord):
            raise ValueError("early-warning graph requires a ScrapedRecallRecord")
        incident = await self.process_record(
            record,
            source_kind=SourceKind(state.get("source_kind", SourceKind.UNKNOWN)),
            trust_tier=TrustTier(state.get("trust_tier", TrustTier.UNKNOWN)),
        )
        return {"incident": incident}

    def _translate(self, record: ScrapedRecallRecord) -> dict[str, Any]:
        envelope = to_translator_envelope(record.payload)
        try:
            translated = self._json_chat(
                system_prompt=TRANSLATION_SYSTEM_PROMPT,
                user_prompt=json.dumps(envelope, ensure_ascii=False),
                model=TRANSLATION_MODEL,
            )
            validate_translated_structure(envelope, translated)
            return translated
        except (AgentOutputError, AgentValidationError, ValueError):
            return envelope

    def _extract(self, translated: dict[str, Any], summary: str) -> IncidentExtraction:
        prompt_payload = {"translated_page": translated, "cautious_summary": summary}
        last_error: Exception | None = None
        for _attempt in range(2):
            user_prompt = json.dumps(prompt_payload, ensure_ascii=False)
            if last_error is not None:
                user_prompt += f"\nPrevious output error: {last_error}. Return valid JSON only."
            try:
                response = self._json_chat(
                    system_prompt=STRUCTURING_PROMPT,
                    user_prompt=user_prompt,
                    model=STRUCTURING_MODEL,
                )
                return IncidentExtraction.model_validate(response)
            except (AgentOutputError, ValueError) as exc:
                last_error = exc
        raise AgentOutputError(f"early-warning incident extraction failed: {last_error}")


def create_early_warning_graph() -> EarlyWarningProcessingService:
    return EarlyWarningProcessingService()


def _to_incident(
    record: ScrapedRecallRecord,
    *,
    taxonomy: TaxonomyResult,
    extraction: IncidentExtraction,
    summary: str,
    source_kind: SourceKind,
    trust_tier: TrustTier,
) -> EarlyWarningIncidentCreate:
    payload = record.payload
    source_url = str(payload.get("canonical_url") or payload.get("source_url") or "").strip()
    if not source_url:
        raise ValueError("processed page is missing a source URL")
    domain = (urlsplit(source_url).hostname or "").lower()
    discovered_at = datetime.now(timezone.utc)
    scraper_date = _sanitize_publication_date(_safe_date(payload.get("publication_date")))
    llm_date = _sanitize_publication_date(extraction.publication_date)
    # Prefer scraper-selected dates over LLM guesses (same as official recalls).
    publication_date = scraper_date or llm_date
    evidence = IncidentEvidence(
        url=source_url,
        title=str(payload.get("title") or ""),
        publication_date=publication_date,
        source_kind=source_kind,
        content_hash=str(payload.get("content_hash") or ""),
        domain=domain,
        publisher=extraction.publisher,
        redirected_url_aliases=[
            str(value)
            for value in payload.get("redirected_url_aliases", [])
            if str(value).strip() and str(value).strip() != source_url
        ],
    )
    return EarlyWarningIncidentCreate(
        incident_type=IncidentType(taxonomy.content_type),
        product_name=extraction.product_name,
        company_name=extraction.company_name,
        product_category=extraction.product_category,
        hazard_type=extraction.hazard_type,
        incident_reason=extraction.incident_reason,
        summary=summary,
        consumer_guidance=extraction.consumer_guidance,
        country=extraction.country,
        affected_regions=extraction.affected_regions,
        publication_date=publication_date,
        first_discovered_at=discovered_at,
        last_discovered_at=discovered_at,
        primary_source_url=source_url,
        primary_source_domain=domain,
        primary_publisher=extraction.publisher,
        source_kind=source_kind,
        trust_tier=trust_tier,
        original_language=extraction.original_language,
        evidence=[evidence],
        extraction_completeness=extraction.extraction_completeness,
    )


def _safe_date(value: object) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _sanitize_publication_date(
    value: date | None,
    *,
    today: date | None = None,
) -> date | None:
    if value is None:
        return None
    current = today or datetime.now(timezone.utc).date()
    if value > current:
        return None
    return value
