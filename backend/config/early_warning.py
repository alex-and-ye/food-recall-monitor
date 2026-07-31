import re
from pathlib import Path
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from settings import get_backend_root

_COUNTRY_CODE_RE = re.compile(r"^[A-Z]{2}$")
_LANGUAGE_CODE_RE = re.compile(r"^[a-z]{2,3}$")

class _StrictConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

def _normalized_strings(value: object, *, lower: bool = False) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("must be a list")
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = str(item).strip()
        if lower:
            text = text.lower()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result

def _normalize_domain(value: object) -> str:
    text = str(value).strip().lower().rstrip(".")
    if not text:
        raise ValueError("domain must be non-empty")
    if "://" in text or any(character in text for character in "/?#@"):
        raise ValueError(f"domain must be a hostname, not a URL: {text}")
    parsed = urlsplit(f"//{text}")
    if not parsed.hostname or parsed.port is not None:
        raise ValueError(f"invalid domain: {text}")
    try:
        return parsed.hostname.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError(f"invalid domain: {text}") from exc

class CountryConfig(_StrictConfigModel):
    code: str
    name: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    languages: list[str] = Field(min_length=1)
    domains: list[str] = Field(default_factory=list)
    enabled: bool = True

    @field_validator("code", mode="before")
    @classmethod
    def _normalize_code(cls, value: object) -> str:
        code = str(value).strip().upper()
        if not _COUNTRY_CODE_RE.fullmatch(code):
            raise ValueError("country code must be a two-letter ISO-style code")
        return code

    @field_validator("name", mode="before")
    @classmethod
    def _normalize_name(cls, value: object) -> str:
        return str(value).strip()

    @field_validator("aliases", mode="before")
    @classmethod
    def _normalize_aliases(cls, value: object) -> list[str]:
        return _normalized_strings(value)

    @field_validator("languages", mode="before")
    @classmethod
    def _normalize_languages(cls, value: object) -> list[str]:
        languages = _normalized_strings(value, lower=True)
        if not languages:
            raise ValueError("at least one language is required")
        return languages

    @field_validator("domains", mode="before")
    @classmethod
    def _normalize_domains(cls, value: object) -> list[str]:
        return [_normalize_domain(item) for item in _normalized_strings(value, lower=True)]

class LanguageTerms(_StrictConfigModel):
    recall: list[str] = Field(min_length=1)
    food: list[str] = Field(min_length=1)
    outbreak: list[str] = Field(default_factory=list)
    illness: list[str] = Field(default_factory=list)
    contamination: list[str] = Field(default_factory=list)
    investigation: list[str] = Field(default_factory=list)

    @field_validator("recall", "food", mode="before")
    @classmethod
    def _normalize_required_terms(cls, value: object) -> list[str]:
        terms = _normalized_strings(value, lower=True)
        if not terms:
            raise ValueError("at least one term is required")
        return terms

    @field_validator(
        "outbreak",
        "illness",
        "contamination",
        "investigation",
        mode="before",
    )
    @classmethod
    def _normalize_optional_terms(cls, value: object) -> list[str]:
        if value is None:
            return []
        return _normalized_strings(value, lower=True)

class DomainConfig(_StrictConfigModel):
    profiles: dict[str, "DomainProfile"] = Field(default_factory=dict)

    @field_validator("profiles", mode="before")
    @classmethod
    def _normalize_profiles(cls, value: object) -> dict[str, object]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("profiles must be a mapping")
        return {_normalize_domain(domain): profile for domain, profile in value.items()}

class DomainProfile(_StrictConfigModel):
    source_kind: str = "unknown"
    trust_tier: str = "unknown"

    @field_validator("source_kind")
    @classmethod
    def _validate_source_kind(cls, value: str) -> str:
        allowed = {
            "official_recall",
            "government_investigation",
            "who_fao",
            "company_release",
            "major_news",
            "trade_publication",
            "unknown",
            "blog",
        }
        normalized = value.strip().lower()
        if normalized not in allowed:
            raise ValueError(f"unknown source kind: {normalized}")
        return normalized

    @field_validator("trust_tier")
    @classmethod
    def _validate_trust_tier(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"official", "high", "medium", "low", "unknown"}:
            raise ValueError(f"unknown trust tier: {normalized}")
        return normalized

class SearchBudgets(_StrictConfigModel):
    queries_per_run: int = Field(default=12, ge=1, le=1000)
    results_per_query: int = Field(default=10, ge=1, le=20)
    candidates_per_run: int = Field(default=200, ge=1, le=10000)
    max_pages_per_query: int = Field(default=1, ge=1, le=10)

class BraveSearchConfig(_StrictConfigModel):
    freshness: str = "pw"
    timeout_seconds: float = Field(default=15.0, gt=0.0, le=120.0)
    minimum_interval_seconds: float = Field(default=1.0, ge=0.0, le=60.0)
    max_retries: int = Field(default=3, ge=0, le=10)
    backoff_seconds: float = Field(default=0.5, ge=0.0, le=60.0)
    jitter_seconds: float = Field(default=0.2, ge=0.0, le=10.0)

    @field_validator("freshness", mode="before")
    @classmethod
    def _validate_freshness(cls, value: object) -> str:
        freshness = str(value).strip().lower()
        if freshness in {"pd", "pw", "pm", "py"}:
            return freshness
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}to\d{4}-\d{2}-\d{2}", freshness):
            return freshness
        raise ValueError("freshness must be pd, pw, pm, py, or a Brave date range")

class CrawlConfig(_StrictConfigModel):
    concurrency: int = Field(default=4, ge=1, le=32)
    minimum_text_characters: int = Field(default=240, ge=1, le=10000)
    timeout_seconds: float = Field(default=20.0, gt=0.0, le=120.0)
    max_attempts: int = Field(default=3, ge=1, le=10)
    retry_delay_minutes: int = Field(default=360, ge=1, le=10080)

class IncidentConfidenceConfig(_StrictConfigModel):
    source_kind_base_weights: dict[str, int] = Field(default_factory=dict)
    corroboration_per_source: int = Field(default=5, ge=0, le=100)
    corroboration_cap: int = Field(default=15, ge=0, le=100)
    explicit_product_modifier: int = Field(default=4, ge=-100, le=100)
    explicit_hazard_modifier: int = Field(default=4, ge=-100, le=100)
    explicit_date_modifier: int = Field(default=2, ge=-100, le=100)
    trusted_domain_modifier: int = Field(default=5, ge=-100, le=100)
    stale_reporting_modifier: int = Field(default=-10, ge=-100, le=100)
    vague_reporting_modifier: int = Field(default=-10, ge=-100, le=100)
    unofficial_cap: int = Field(default=99, ge=0, le=100)

    @field_validator("source_kind_base_weights", mode="before")
    @classmethod
    def _validate_base_weights(cls, value: object) -> dict[str, int]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("source_kind_base_weights must be a mapping")
        allowed = {
            "official_recall",
            "government_investigation",
            "who_fao",
            "company_release",
            "major_news",
            "trade_publication",
            "unknown",
            "blog",
        }
        normalized: dict[str, int] = {}
        for raw_kind, raw_weight in value.items():
            kind = str(raw_kind).strip().lower()
            if kind not in allowed:
                raise ValueError(f"unknown source kind weight: {kind}")
            weight = int(raw_weight)
            if not 0 <= weight <= 100:
                raise ValueError("source kind weights must be between 0 and 100")
            normalized[kind] = weight
        return normalized

class SemanticMatchingConfig(_StrictConfigModel):
    enabled: bool = False
    collection_name: str = Field(default="safety_event_similarity_v1", min_length=3)
    model_name: str = Field(default="all-MiniLM-L6-v2", min_length=1)
    review_threshold: float = Field(default=0.82, ge=0.0, le=1.0)
    auto_merge_threshold: float = Field(default=0.92, ge=0.0, le=1.0)
    result_limit: int = Field(default=10, ge=1, le=100)

    @model_validator(mode="after")
    def _validate_thresholds(self) -> SemanticMatchingConfig:
        if self.review_threshold > self.auto_merge_threshold:
            raise ValueError("semantic review threshold must not exceed auto-merge threshold")
        return self

class EarlyWarningConfig(_StrictConfigModel):
    countries: list[CountryConfig] = Field(min_length=1)
    languages: dict[str, LanguageTerms] = Field(min_length=1)
    domains: DomainConfig = Field(default_factory=DomainConfig)
    budgets: SearchBudgets = Field(default_factory=SearchBudgets)
    brave: BraveSearchConfig = Field(default_factory=BraveSearchConfig)
    crawl: CrawlConfig = Field(default_factory=CrawlConfig)
    incident_confidence: IncidentConfidenceConfig = Field(default_factory=IncidentConfidenceConfig)
    semantic_matching: SemanticMatchingConfig = Field(default_factory=SemanticMatchingConfig)
    # Runtime switch injected from config/pipelines.yaml — not set in this file.
    enabled: bool = False

    @field_validator("languages", mode="before")
    @classmethod
    def _normalize_language_keys(cls, value: object) -> dict[str, object]:
        if not isinstance(value, dict):
            raise ValueError("languages must be a mapping")
        normalized: dict[str, object] = {}
        for raw_code, terms in value.items():
            code = str(raw_code).strip().lower()
            if not _LANGUAGE_CODE_RE.fullmatch(code):
                raise ValueError(f"invalid language code: {code}")
            if code in normalized:
                raise ValueError(f"duplicate language code: {code}")
            normalized[code] = terms
        return normalized

    @model_validator(mode="after")
    def _validate_references(self) -> EarlyWarningConfig:
        country_codes = [country.code for country in self.countries]
        if len(country_codes) != len(set(country_codes)):
            raise ValueError("country codes must be unique")
        unknown_languages = {
            language
            for country in self.countries
            for language in country.languages
            if language not in self.languages
        }
        if unknown_languages:
            raise ValueError(f"countries reference unknown languages: {sorted(unknown_languages)}")
        return self

    def validate_runtime(self, *, brave_api_key: str | None) -> None:
        if self.enabled and not (brave_api_key or "").strip():
            raise ValueError("BRAVE_API_KEY is required when early warning is enabled")

DEFAULT_EARLY_WARNING_CONFIG_PATH = get_backend_root() / "config" / "early_warning.yaml"

def load_early_warning_config(path: str | Path | None = None) -> EarlyWarningConfig:
    config_path = Path(path) if path is not None else DEFAULT_EARLY_WARNING_CONFIG_PATH
    if not config_path.is_absolute():
        config_path = get_backend_root() / config_path
    with config_path.open("r", encoding="utf-8") as config_file:
        payload = yaml.safe_load(config_file)
    if not isinstance(payload, dict):
        raise ValueError(f"early warning config must be a mapping: {config_path}")
    if "enabled" in payload:
        raise ValueError(
            "early_warning.yaml must not set 'enabled'; "
            "configure early_warning.enabled in config/pipelines.yaml instead"
        )
    return EarlyWarningConfig.model_validate(payload)
