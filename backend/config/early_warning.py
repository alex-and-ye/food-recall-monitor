"""Early-warning discovery configuration loaded from ``early_warning.yaml``.

Defines countries, language search terms, domain trust profiles, Brave/crawl
budgets, incident confidence weights, and optional semantic matching.
Runtime ``enabled`` is injected from ``pipelines.yaml``, not this file.
"""

import re
from pathlib import Path
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from settings import get_backend_root

# Matches ISO-style two-letter country codes
_COUNTRY_CODE_RE = re.compile(r"^[A-Z]{2}$")
# Matches short language codes (2–3 lowercase letters)
_LANGUAGE_CODE_RE = re.compile(r"^[a-z]{2,3}$")


class _StrictConfigModel(BaseModel):
    """Pydantic base that forbids unexpected YAML keys."""

    model_config = ConfigDict(extra="forbid")


def _normalized_strings(value: object, *, lower: bool = False) -> list[str]:
    """Normalize a list of strings: strip, optionally lower, dedupe.

    Args:
        value: Expected list of string-convertible items.
        lower: When True, lowercases each item.

    Returns:
        Deduplicated list of non-empty strings preserving first-seen order.

    Raises:
        ValueError: If ``value`` is not a list.
    """
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
    """Normalize a hostname string to ASCII IDNA form.

    Args:
        value: Raw domain or hostname (not a full URL).

    Returns:
        Lowercased ASCII hostname without trailing dots.

    Raises:
        ValueError: If empty, looks like a URL, or is otherwise invalid.
    """
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
    """Per-country early-warning search targeting.

    Attributes:
        code: Two-letter ISO-style country code.
        name: Human-readable country name.
        aliases: Alternate names used in queries.
        languages: Language codes that must exist in ``languages``.
        domains: Preferred hostnames associated with the country.
        enabled: When False, exclude from discovery runs.
    """

    code: str
    name: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    languages: list[str] = Field(min_length=1)
    domains: list[str] = Field(default_factory=list)
    enabled: bool = True

    @field_validator("code", mode="before")
    @classmethod
    def _normalize_code(cls, value: object) -> str:
        """Uppercase and validate a two-letter country code.

        Args:
            value: Raw country code value from YAML.

        Returns:
            Normalized uppercase country code.

        Raises:
            ValueError: If the code is not two letters.
        """
        code = str(value).strip().upper()
        if not _COUNTRY_CODE_RE.fullmatch(code):
            raise ValueError("country code must be a two-letter ISO-style code")
        return code

    @field_validator("name", mode="before")
    @classmethod
    def _normalize_name(cls, value: object) -> str:
        """Strip surrounding whitespace from the country name.

        Args:
            value: Raw name value from YAML.

        Returns:
            Stripped name string.
        """
        return str(value).strip()

    @field_validator("aliases", mode="before")
    @classmethod
    def _normalize_aliases(cls, value: object) -> list[str]:
        """Normalize the aliases list.

        Args:
            value: Raw aliases list from YAML.

        Returns:
            Deduplicated stripped aliases.
        """
        return _normalized_strings(value)

    @field_validator("languages", mode="before")
    @classmethod
    def _normalize_languages(cls, value: object) -> list[str]:
        """Normalize language codes and require at least one.

        Args:
            value: Raw languages list from YAML.

        Returns:
            Lowercased, deduplicated language codes.

        Raises:
            ValueError: If no languages remain after normalization.
        """
        languages = _normalized_strings(value, lower=True)
        if not languages:
            raise ValueError("at least one language is required")
        return languages

    @field_validator("domains", mode="before")
    @classmethod
    def _normalize_domains(cls, value: object) -> list[str]:
        """Normalize country-associated domain hostnames.

        Args:
            value: Raw domains list from YAML.

        Returns:
            List of IDNA-normalized hostnames.
        """
        return [_normalize_domain(item) for item in _normalized_strings(value, lower=True)]


class LanguageTerms(_StrictConfigModel):
    """Search vocabulary for a single language.

    Attributes:
        recall: Required terms related to recalls/withdrawals.
        food: Required terms related to food products.
        outbreak: Optional outbreak-related terms.
        illness: Optional illness-related terms.
        contamination: Optional contamination-related terms.
        investigation: Optional investigation-related terms.
    """

    recall: list[str] = Field(min_length=1)
    food: list[str] = Field(min_length=1)
    outbreak: list[str] = Field(default_factory=list)
    illness: list[str] = Field(default_factory=list)
    contamination: list[str] = Field(default_factory=list)
    investigation: list[str] = Field(default_factory=list)

    @field_validator("recall", "food", mode="before")
    @classmethod
    def _normalize_required_terms(cls, value: object) -> list[str]:
        """Normalize required term lists and reject empty results.

        Args:
            value: Raw term list from YAML.

        Returns:
            Lowercased, deduplicated terms.

        Raises:
            ValueError: If no terms remain after normalization.
        """
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
        """Normalize optional term lists; treat ``None`` as empty.

        Args:
            value: Raw term list or ``None`` from YAML.

        Returns:
            Lowercased, deduplicated terms, or an empty list.
        """
        if value is None:
            return []
        return _normalized_strings(value, lower=True)


class DomainConfig(_StrictConfigModel):
    """Mapping of hostnames to trust / source-kind profiles.

    Attributes:
        profiles: Hostname-keyed domain profiles.
    """

    profiles: dict[str, "DomainProfile"] = Field(default_factory=dict)

    @field_validator("profiles", mode="before")
    @classmethod
    def _normalize_profiles(cls, value: object) -> dict[str, object]:
        """Normalize profile map keys to IDNA hostnames.

        Args:
            value: Raw profiles mapping or ``None``.

        Returns:
            Dict with normalized domain keys.

        Raises:
            ValueError: If ``value`` is not a mapping (when not ``None``).
        """
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("profiles must be a mapping")
        return {_normalize_domain(domain): profile for domain, profile in value.items()}


class DomainProfile(_StrictConfigModel):
    """Trust metadata for a single hostname.

    Attributes:
        source_kind: Classification of the publisher (e.g. ``major_news``).
        trust_tier: Trust level (``official``, ``high``, ``medium``, ``low``,
            or ``unknown``).
    """

    source_kind: str = "unknown"
    trust_tier: str = "unknown"

    @field_validator("source_kind")
    @classmethod
    def _validate_source_kind(cls, value: str) -> str:
        """Validate and lowercase a source-kind string.

        Args:
            value: Raw source-kind value.

        Returns:
            Normalized source-kind string.

        Raises:
            ValueError: If the value is not in the allowed set.
        """
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
        """Validate and lowercase a trust-tier string.

        Args:
            value: Raw trust-tier value.

        Returns:
            Normalized trust-tier string.

        Raises:
            ValueError: If the value is not in the allowed set.
        """
        normalized = value.strip().lower()
        if normalized not in {"official", "high", "medium", "low", "unknown"}:
            raise ValueError(f"unknown trust tier: {normalized}")
        return normalized


class SearchBudgets(_StrictConfigModel):
    """Per-run limits for Brave search and candidate collection.

    Attributes:
        queries_per_run: Max search queries issued in one discovery run.
        results_per_query: Max results requested per Brave query.
        candidates_per_run: Cap on candidates retained per run.
        max_pages_per_query: Max Brave result pages fetched per query.
    """

    queries_per_run: int = Field(default=12, ge=1, le=1000)
    results_per_query: int = Field(default=10, ge=1, le=20)
    candidates_per_run: int = Field(default=200, ge=1, le=10000)
    max_pages_per_query: int = Field(default=1, ge=1, le=10)


class BraveSearchConfig(_StrictConfigModel):
    """HTTP client settings for Brave web search.

    Attributes:
        freshness: Brave freshness filter (``pd``/``pw``/``pm``/``py`` or
            a date-range string).
        timeout_seconds: Per-request timeout.
        minimum_interval_seconds: Minimum delay between requests.
        max_retries: Retry count on transient failures.
        backoff_seconds: Base backoff between retries.
        jitter_seconds: Random jitter added to backoff.
    """

    freshness: str = "pw"
    timeout_seconds: float = Field(default=15.0, gt=0.0, le=120.0)
    minimum_interval_seconds: float = Field(default=1.0, ge=0.0, le=60.0)
    max_retries: int = Field(default=3, ge=0, le=10)
    backoff_seconds: float = Field(default=0.5, ge=0.0, le=60.0)
    jitter_seconds: float = Field(default=0.2, ge=0.0, le=10.0)

    @field_validator("freshness", mode="before")
    @classmethod
    def _validate_freshness(cls, value: object) -> str:
        """Validate Brave freshness presets or date-range form.

        Args:
            value: Raw freshness value from YAML.

        Returns:
            Normalized lowercase freshness string.

        Raises:
            ValueError: If the value is not a known preset or date range.
        """
        freshness = str(value).strip().lower()
        if freshness in {"pd", "pw", "pm", "py"}:
            return freshness
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}to\d{4}-\d{2}-\d{2}", freshness):
            return freshness
        raise ValueError("freshness must be pd, pw, pm, py, or a Brave date range")


class CrawlConfig(_StrictConfigModel):
    """Page-fetch settings for candidate URL scraping.

    Attributes:
        concurrency: Max concurrent page fetches.
        minimum_text_characters: Minimum extracted text length to accept.
        timeout_seconds: Per-page fetch timeout.
        max_attempts: Max fetch attempts per URL.
        retry_delay_minutes: Delay before retrying a failed URL.
    """

    concurrency: int = Field(default=4, ge=1, le=32)
    minimum_text_characters: int = Field(default=240, ge=1, le=10000)
    timeout_seconds: float = Field(default=20.0, gt=0.0, le=120.0)
    max_attempts: int = Field(default=3, ge=1, le=10)
    retry_delay_minutes: int = Field(default=360, ge=1, le=10080)


class IncidentConfidenceConfig(_StrictConfigModel):
    """Weights and modifiers for incident confidence scoring.

    Attributes:
        source_kind_base_weights: Overrides for per-source-kind base scores.
        corroboration_per_source: Points added per corroborating source.
        corroboration_cap: Maximum corroboration bonus.
        explicit_product_modifier: Bonus when product is explicit.
        explicit_hazard_modifier: Bonus when hazard is explicit.
        explicit_date_modifier: Bonus when date is explicit.
        trusted_domain_modifier: Bonus for trusted domains.
        stale_reporting_modifier: Penalty for stale reporting.
        vague_reporting_modifier: Penalty for vague reporting.
        unofficial_cap: Max confidence for unofficial-only incidents.
    """

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
        """Validate and normalize source-kind weight overrides.

        Args:
            value: Raw mapping or ``None`` from YAML.

        Returns:
            Dict of allowed source kinds to integer weights in ``[0, 100]``.

        Raises:
            ValueError: If the value is not a mapping, has unknown keys, or
                weights are out of range.
        """
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
    """Optional embedding-based incident/alert similarity settings.

    Attributes:
        enabled: When True, build and use the semantic index.
        collection_name: Chroma collection for embeddings.
        model_name: Sentence-transformer model name.
        review_threshold: Similarity at or above which manual review is suggested.
        auto_merge_threshold: Similarity at or above which auto-merge applies.
        result_limit: Max similar neighbors returned per query.
    """

    enabled: bool = False
    collection_name: str = Field(default="safety_event_similarity_v1", min_length=3)
    model_name: str = Field(default="all-MiniLM-L6-v2", min_length=1)
    review_threshold: float = Field(default=0.82, ge=0.0, le=1.0)
    auto_merge_threshold: float = Field(default=0.92, ge=0.0, le=1.0)
    result_limit: int = Field(default=10, ge=1, le=100)

    @model_validator(mode="after")
    def _validate_thresholds(self) -> SemanticMatchingConfig:
        """Ensure review threshold does not exceed auto-merge threshold.

        Returns:
            This config instance when thresholds are consistent.

        Raises:
            ValueError: If ``review_threshold`` > ``auto_merge_threshold``.
        """
        if self.review_threshold > self.auto_merge_threshold:
            raise ValueError("semantic review threshold must not exceed auto-merge threshold")
        return self


class EarlyWarningConfig(_StrictConfigModel):
    """Root early-warning configuration document.

    Attributes:
        countries: Targeted countries for discovery.
        languages: Language code to search-term vocabulary.
        domains: Domain trust profiles.
        budgets: Per-run search and candidate limits.
        brave: Brave Search client settings.
        crawl: Page crawl settings.
        incident_confidence: Confidence scoring weights.
        semantic_matching: Optional semantic similarity settings.
        enabled: Runtime switch injected from ``pipelines.yaml``.
    """

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
        """Normalize and validate language map keys.

        Args:
            value: Raw languages mapping from YAML.

        Returns:
            Dict with lowercase language-code keys.

        Raises:
            ValueError: If not a mapping, keys are invalid, or keys duplicate.
        """
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
        """Ensure country codes are unique and language refs exist.

        Returns:
            This config instance when cross-references are valid.

        Raises:
            ValueError: On duplicate country codes or unknown language refs.
        """
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
        """Validate runtime requirements when early warning is enabled.

        Args:
            brave_api_key: Brave Search API key from application settings.

        Raises:
            ValueError: If enabled but ``brave_api_key`` is missing/blank.
        """
        if self.enabled and not (brave_api_key or "").strip():
            raise ValueError("BRAVE_API_KEY is required when early warning is enabled")


# Default path to early_warning.yaml under the backend package
DEFAULT_EARLY_WARNING_CONFIG_PATH = get_backend_root() / "config" / "early_warning.yaml"


def load_early_warning_config(path: str | Path | None = None) -> EarlyWarningConfig:
    """Load and validate early-warning config from YAML.

    The YAML must not set ``enabled``; that flag comes from ``pipelines.yaml``.

    Args:
        path: Optional path to ``early_warning.yaml``. Relative paths are
            resolved against the backend root. Defaults to
            ``DEFAULT_EARLY_WARNING_CONFIG_PATH``.

    Returns:
        Validated ``EarlyWarningConfig`` (with ``enabled`` still default False
        until callers inject the pipeline switch).

    Raises:
        ValueError: If the YAML root is not a mapping or contains ``enabled``.
    """
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
