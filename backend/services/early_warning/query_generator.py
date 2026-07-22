from __future__ import annotations

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


def _quoted(term: str) -> str:
    escaped = term.replace('"', " ")
    normalized = " ".join(escaped.split())
    return f'"{normalized}"' if " " in normalized else normalized


def build_query_catalog(config: EarlyWarningConfig) -> list[SearchQuery]:
    """Build the complete query catalog in a stable, configuration-driven order."""
    queries: list[SearchQuery] = []
    seen_text: set[tuple[str, str, str, str | None]] = set()
    for country in config.countries:
        if not country.enabled:
            continue
        for language in country.languages:
            language_terms = config.languages[language]
            domains: list[str | None] = [None, *country.domains]
            intent_terms = list(
                dict.fromkeys(
                    [
                        *language_terms.recall,
                        *language_terms.outbreak,
                        *language_terms.illness,
                        *language_terms.contamination,
                        *language_terms.investigation,
                    ]
                )
            )
            country_names = list(dict.fromkeys([country.name, *country.aliases]))
            for country_name in country_names:
                for recall_term in intent_terms:
                    for food_term in language_terms.food:
                        for domain in domains:
                            parts = [
                                _quoted(recall_term),
                                _quoted(food_term),
                                _quoted(country_name),
                            ]
                            if domain is not None:
                                parts.append(f"site:{domain}")
                            text = " ".join(parts)
                            identity = (text, country.code, language, domain)
                            if identity in seen_text:
                                continue
                            seen_text.add(identity)
                            queries.append(
                                SearchQuery.create(
                                    text=text,
                                    country=country.code,
                                    language=language,
                                    domain=domain,
                                )
                            )
    return queries


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
