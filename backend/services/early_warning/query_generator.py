from config.early_warning import EarlyWarningConfig
from models.search_candidate import SearchQuery

class QueryGenerator:
    def __init__(self, config: EarlyWarningConfig) -> None:
        self._config = config

    def catalog(self) -> list[SearchQuery]:
        return build_query_catalog(self._config)

    def generate(
        self,
        *,
        rotation: int = 0,
        budget: int | None = None,
    ) -> list[SearchQuery]:
        return generate_queries(self._config, rotation=rotation, budget=budget)

def build_query_catalog(config: EarlyWarningConfig) -> list[SearchQuery]:
    """Build discovery queries with recall intents first.

    Broad illness/contamination queries are appended later so rotation does not
    spend the whole budget on low-precision matches. Site probes stay last.
    """
    queries_by_country: dict[str, list[SearchQuery]] = {}
    seen_text: set[tuple[str, str, str, str | None]] = set()

    def add(
        *,
        text: str,
        country_code: str,
        language: str,
        domain: str | None = None,
    ) -> None:
        normalized = " ".join(text.split())
        if not normalized:
            return
        identity = (normalized, country_code, language, domain)
        if identity in seen_text:
            return
        seen_text.add(identity)
        queries_by_country.setdefault(country_code, []).append(
            SearchQuery.create(
                text=normalized,
                country=country_code,
                language=language,
                domain=domain,
            )
        )

    for country in config.countries:
        if not country.enabled:
            continue
        for language in country.languages:
            language_terms = config.languages[language]
            country_names = list(dict.fromkeys([country.name, *country.aliases]))
            secondary_intents = list(
                dict.fromkeys(
                    [
                        *language_terms.outbreak,
                        *language_terms.illness,
                        *language_terms.contamination,
                        *language_terms.investigation,
                    ]
                )
            )

            for country_name in country_names:
                for intent in language_terms.recall:
                    add(
                        text=f"{intent} {country_name}",
                        country_code=country.code,
                        language=language,
                    )

            primary_name = country.name
            for intent in secondary_intents:
                add(
                    text=f"{intent} {primary_name}",
                    country_code=country.code,
                    language=language,
                )

            for domain in country.domains:
                for intent in language_terms.recall[:2]:
                    add(
                        text=f"{intent} site:{domain}",
                        country_code=country.code,
                        language=language,
                        domain=domain,
                    )
    return _interleave_country_queries(queries_by_country)

def generate_queries(
    config: EarlyWarningConfig,
    *,
    rotation: int = 0,
    budget: int | None = None,
) -> list[SearchQuery]:
    """Return a deterministic cyclic slice so successive runs cover the catalog."""
    if rotation < 0:
        raise ValueError("rotation must be non-negative")
    limit = config.budgets.queries_per_run if budget is None else budget
    if limit < 0:
        raise ValueError("budget must be non-negative")
    if limit == 0:
        return []
    catalog = build_query_catalog(config)
    if not catalog:
        return []
    count = min(limit, len(catalog))
    start = (rotation * count) % len(catalog)
    return [catalog[(start + index) % len(catalog)] for index in range(count)]

def _interleave_country_queries(
    queries_by_country: dict[str, list[SearchQuery]],
) -> list[SearchQuery]:
    """Distribute country coverage throughout the catalog.

    A country can contribute many aliases and site probes. Keeping each
    country's queries contiguous starves later countries whenever the per-run
    query budget is smaller than the first country's catalog slice.
    """
    country_codes = list(queries_by_country)
    positions = {country_code: 0 for country_code in country_codes}
    queries: list[SearchQuery] = []

    while True:
        added = False
        for country_code in country_codes:
            index = positions[country_code]
            country_queries = queries_by_country[country_code]
            if index >= len(country_queries):
                continue
            queries.append(country_queries[index])
            positions[country_code] += 1
            added = True
        if not added:
            return queries
