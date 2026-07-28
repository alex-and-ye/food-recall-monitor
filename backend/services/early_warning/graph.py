from __future__ import annotations

import asyncio
import json
import re
import unicodedata
from collections.abc import Callable
from datetime import date, datetime, timezone
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator

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

_SOURCE_KIND_VALUES = {item.value for item in SourceKind}
_CONTENT_TAXONOMY_VALUES = {
    "official_recall",
    "potential_recall",
    "foodborne_outbreak",
    "investigation",
    "company_withdrawal",
    "public_health_warning",
    "food_safety_advisory",
    "irrelevant",
}
_DEFAULT_TRUST_BY_SOURCE_KIND: dict[SourceKind, TrustTier] = {
    SourceKind.OFFICIAL_RECALL: TrustTier.OFFICIAL,
    SourceKind.GOVERNMENT_INVESTIGATION: TrustTier.OFFICIAL,
    SourceKind.WHO_FAO: TrustTier.HIGH,
    SourceKind.COMPANY_RELEASE: TrustTier.HIGH,
    SourceKind.MAJOR_NEWS: TrustTier.MEDIUM,
    SourceKind.TRADE_PUBLICATION: TrustTier.MEDIUM,
    SourceKind.BLOG: TrustTier.LOW,
    SourceKind.UNKNOWN: TrustTier.UNKNOWN,
}
_NON_FOOD_PRODUCT_TERMS = (
    "appliance",
    "automobile",
    "battery",
    "car",
    "charger",
    "computer",
    "cosmetic",
    "electronics",
    "electronic device",
    "furniture",
    "laptop",
    "mobile phone",
    "motorcycle",
    "power bank",
    "smartphone",
    "television",
    "toy",
    "tyre",
    "vehicle",
    "appareil electronique",
    "telephone",
    "jouet",
    "meuble",
    "cosmetique",
    "fahrzeug",
    "elektronik",
    "elektrogerat",
    "spielzeug",
)

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

TAXONOMY_PROMPT = """Classify the supplied page using exactly one content_type.
Return ONLY this JSON shape:
{"content_type":"<one allowed value>","reason":"<short justification>"}
Allowed content_type values:
official_recall, potential_recall, foodborne_outbreak, investigation,
company_withdrawal, public_health_warning, food_safety_advisory, irrelevant.
Use irrelevant for historical summaries, generic food advice, unrelated products,
encyclopedia/list pages, or pages without a current concrete food-safety event.
Use irrelevant for every non-food recall, including electronics, batteries,
vehicles, toys, furniture, cosmetics, household appliances, and software.
Do not infer a recall merely from cautious or speculative wording.
Never return MIME types, nested product objects, or any keys other than
content_type and reason."""

BORDERLINE_PROMPT = """Decide whether this search-result metadata is sufficiently
likely to describe a current, concrete food-safety incident to justify fetching.
Accept ONLY alerts about food, beverages, dietary supplements, or food-contact
materials: recalls, withdrawals, outbreaks, illness clusters, contamination reports,
investigations, public-health warnings, and food-safety advisories. The alert itself
must be food-related; do not accept it merely because the source, search query, or
surrounding text mentions food. Reject generic advice, recipes, historical pages,
encyclopedia pages, and every non-food product recall (including electronics,
batteries, vehicles, toys, furniture, cosmetics, appliances, and software). When
the metadata does not explicitly support a food-related safety incident, reject it.
Return JSON:
{"relevant": true|false, "reason": "..."}."""

SUMMARY_PROMPT = """Write a concise factual summary of the supplied food-safety page.
Preserve uncertainty and attribution. Never upgrade an investigation, allegation,
or potential issue into a confirmed recall. Include consumer guidance only when the
source explicitly provides it. Return plain text only."""

STRUCTURING_PROMPT = """Extract one current food-safety incident from the supplied
translated page and summary. Return one JSON object with these keys:
product_name, company_name, product_category, hazard_type, incident_reason,
consumer_guidance, country, affected_regions (array), publication_date (YYYY-MM-DD
or null), publisher, source_kind, original_language, extraction_completeness (0..1).
All of product_name, company_name, product_category, hazard_type, incident_reason,
consumer_guidance, country, publisher, and original_language MUST be strings
(not arrays/objects). If multiple hazards apply, join them in one hazard_type
string with "; ". Use empty strings/arrays for facts not supported by the source.
Do not invent facts.

product_name must contain only the concise name of ONE affected product or one
clearly defined product range.
Extract food, beverages, food supplements, or food-contact items only. If the
page is about electronics, batteries, vehicles, toys, furniture, cosmetics,
appliances, software, or another non-food item, leave product_name empty.

Classify source_kind from the publisher/outlet type of THIS page (not the incident
type). Choose exactly one of:
- official_recall: national/regional food-safety authority recall notices
- government_investigation: other government agency investigation or outbreak notices
- who_fao: WHO, FAO, or similar international public-health organization pages
- company_release: manufacturer, retailer, or brand's own notice/press release
- major_news: general news media, newspapers, broadcasters, or news portals
- trade_publication: food-industry or food-safety specialty journalism
- blog: personal blogs, forums, opinion, or unverified commentary
- unknown: only when the outlet type truly cannot be determined
Prefer major_news for ordinary news reporting. Do not use domain allowlists; judge
from page content, byline, publisher name, and how the outlet presents itself."""


class TaxonomyResult(BaseModel):
    content_type: ContentTaxonomy
    reason: str = ""

    @field_validator("content_type", mode="before")
    @classmethod
    def _coerce_content_type(cls, value: object) -> object:
        text = str(value or "").strip().lower()
        if text in _CONTENT_TAXONOMY_VALUES:
            return text
        raise ValueError(
            "content_type must be one of: " + ", ".join(sorted(_CONTENT_TAXONOMY_VALUES))
        )

    @field_validator("reason", mode="before")
    @classmethod
    def _coerce_reason(cls, value: object) -> str:
        return _coerce_string(value)


class BorderlineRelevance(BaseModel):
    relevant: bool
    reason: str = ""

    @field_validator("reason", mode="before")
    @classmethod
    def _coerce_reason(cls, value: object) -> str:
        return _coerce_string(value)


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
    source_kind: SourceKind = SourceKind.UNKNOWN
    original_language: str = ""
    extraction_completeness: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator(
        "product_name",
        "company_name",
        "product_category",
        "hazard_type",
        "incident_reason",
        "consumer_guidance",
        "country",
        "publisher",
        "original_language",
        mode="before",
    )
    @classmethod
    def _coerce_text_fields(cls, value: object) -> str:
        return _coerce_string(value)

    @field_validator("affected_regions", mode="before")
    @classmethod
    def _coerce_regions(cls, value: object) -> list[str]:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            parts = [part.strip() for part in value.replace(";", ",").split(",")]
            return [part for part in parts if part]
        if isinstance(value, list):
            return [text for item in value if (text := _coerce_string(item))]
        return [_coerce_string(value)]

    @field_validator("source_kind", mode="before")
    @classmethod
    def _coerce_source_kind(cls, value: object) -> object:
        if value is None:
            return SourceKind.UNKNOWN
        text = str(value).strip().lower()
        if not text or text not in _SOURCE_KIND_VALUES:
            return SourceKind.UNKNOWN
        return text


def _coerce_string(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "; ".join(
            part for item in value if (part := _coerce_string(item))
        )
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value).strip()


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
        # Ollama's Python client is synchronous. Run the complete inference
        # sequence off the FastAPI event loop so API requests stay responsive
        # while a discovery pipeline is processing records.
        return await asyncio.to_thread(
            self._process_record_sync,
            record,
            source_kind=source_kind,
            trust_tier=trust_tier,
        )

    def _process_record_sync(
        self,
        record: ScrapedRecallRecord,
        *,
        source_kind: SourceKind,
        trust_tier: TrustTier,
    ) -> EarlyWarningIncidentCreate | None:
        translated = self._translate(record)
        taxonomy = self._classify(translated)
        if taxonomy.content_type == "irrelevant":
            return None

        summary = self._text_chat(
            system_prompt=SUMMARY_PROMPT,
            user_prompt=json.dumps(translated, ensure_ascii=False),
        ).strip()
        if not summary:
            raise AgentOutputError("early-warning summary was empty")
        extraction = self._extract(translated, summary)
        extraction = extraction.model_copy(
            update={
                "product_name": _clean_header_value(extraction.product_name),
                "company_name": _clean_header_value(extraction.company_name),
            }
        )
        if _requires_specific_product(taxonomy.content_type) and not _is_specific_product(
            extraction.product_name
        ):
            return None
        if _is_explicitly_non_food(extraction):
            return None
        resolved_kind, resolved_trust = _resolve_source_profile(
            configured_kind=source_kind,
            configured_trust=trust_tier,
            extracted_kind=extraction.source_kind,
        )
        return _to_incident(
            record,
            taxonomy=taxonomy,
            extraction=extraction,
            summary=summary,
            source_kind=resolved_kind,
            trust_tier=resolved_trust,
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

    def _classify(self, translated: dict[str, Any]) -> TaxonomyResult:
        last_error: Exception | None = None
        for _attempt in range(2):
            user_prompt = json.dumps(translated, ensure_ascii=False)
            if last_error is not None:
                user_prompt += (
                    f"\nPrevious output error: {last_error}. "
                    'Return only {"content_type":"...","reason":"..."} with an allowed content_type.'
                )
            try:
                response = self._json_chat(
                    system_prompt=TAXONOMY_PROMPT,
                    user_prompt=user_prompt,
                    model=CLASSIFICATION_MODEL,
                )
                return TaxonomyResult.model_validate(_normalize_taxonomy_payload(response))
            except (AgentOutputError, ValueError) as exc:
                last_error = exc
        raise AgentOutputError(f"early-warning taxonomy failed: {last_error}")

    def _extract(self, translated: dict[str, Any], summary: str) -> IncidentExtraction:
        prompt_payload = {"translated_page": translated, "cautious_summary": summary}
        last_error: Exception | None = None
        for _attempt in range(2):
            user_prompt = json.dumps(prompt_payload, ensure_ascii=False)
            if last_error is not None:
                user_prompt += (
                    f"\nPrevious output error: {last_error}. Return valid JSON only. "
                    "hazard_type and other scalar fields must be strings, not arrays."
                )
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


def _normalize_taxonomy_payload(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("taxonomy response must be a JSON object")
    data = dict(payload)
    if "content_type" not in data:
        for key in ("type", "classification", "category", "label"):
            if key in data:
                data["content_type"] = data[key]
                break
    return data


def _clean_header_value(value: str, *, maximum: int = 160) -> str:
    """Keep card headers concise and free of copied markup/JSON."""
    text = " ".join(str(value or "").split()).strip(" \t\r\n-–—|:;\"'")
    if len(text) > maximum or text.startswith(("{", "[")):
        return ""
    return text


def _requires_specific_product(content_type: ContentTaxonomy) -> bool:
    return content_type in {
        "official_recall",
        "potential_recall",
        "company_withdrawal",
    }


def _is_specific_product(product_name: str) -> bool:
    text = _clean_header_value(product_name)
    normalized = " ".join(text.casefold().split())
    if not normalized:
        return False
    vague_names = {
        "various products",
        "multiple products",
        "food products",
        "recalled products",
        "product recalls",
        "recall alerts",
        "food recalls",
        "all products",
    }
    if normalized in vague_names:
        return False
    # A detail title can contain a small family of closely related variants, but
    # a long delimiter-heavy value is almost always a listing copied by the LLM.
    separators = text.count(",") + text.count(";") + text.count("|")
    return separators < 4 and normalized.count(" and ") < 4


def _is_explicitly_non_food(extraction: IncidentExtraction) -> bool:
    """Block clearly non-food recalls even if an LLM assigns food taxonomy."""
    text = " ".join(
        (
            extraction.product_name,
            extraction.product_category,
            extraction.incident_reason,
        )
    ).casefold()
    ascii_text = "".join(
        character
        for character in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(character)
    )
    normalized = re.sub(r"[^a-z0-9]+", " ", ascii_text)
    return any(
        re.search(rf"\b{re.escape(term)}\b", normalized) is not None
        for term in _NON_FOOD_PRODUCT_TERMS
    )


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


def _resolve_source_profile(
    *,
    configured_kind: SourceKind,
    configured_trust: TrustTier,
    extracted_kind: SourceKind,
) -> tuple[SourceKind, TrustTier]:
    """Prefer optional domain-profile overrides; otherwise use LLM classification."""
    source_kind = (
        configured_kind
        if configured_kind != SourceKind.UNKNOWN
        else extracted_kind
    )
    if configured_trust != TrustTier.UNKNOWN:
        return source_kind, configured_trust
    return source_kind, _DEFAULT_TRUST_BY_SOURCE_KIND.get(
        source_kind, TrustTier.UNKNOWN
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
