from __future__ import annotations

from models.scraper_config import ScraperHints, ScraperSourceConfig

ScraperSourceRegistry = dict[str, ScraperSourceConfig]

TRANSLATION_MODEL: str = "qwen2.5:14b"
SUMMARIZATION_MODEL: str = "qwen2.5:14b"
STRUCTURING_MODEL: str = "qwen2.5:14b"

OLLAMA_OPTIONS: dict[str, float | int] = {
    "temperature": 0.0,
    "num_ctx": 4096,
    "num_gpu": 99,
}

SCRAPER_SOURCES: ScraperSourceRegistry = {
    "france": ScraperSourceConfig(
        base_url="https://rappel.conso.gouv.fr",
        allowed_domains=["rappel.conso.gouv.fr"],
        seed_urls=["https://rappel.conso.gouv.fr/categorie/1?#navigation"],
        max_depth=2,
        max_pages_per_run=50,
        lookback_days=1,
        hints=ScraperHints(
            recall_keywords=["rappel", "alerte", "retrait", "allergene", "salmonella"],
            date_selectors=["time", ".date", "[datetime]"],
            blocked_paths=["/faq", "/mentions-legales", "/parametres"],
        ),
    ),
    "uk": ScraperSourceConfig(
        base_url="https://www.food.gov.uk",
        allowed_domains=["www.food.gov.uk", "food.gov.uk"],
        seed_urls=[
            "https://www.food.gov.uk/search?keywords=&filter_type%5BFood%20alert%5D=Food%20alert",
        ],
        max_depth=2,
        max_pages_per_run=40,
        lookback_days=1,
        hints=ScraperHints(
            recall_keywords=["recall", "food alert", "allergy alert", "withdrawal", "salmonella"],
            date_selectors=["time", ".published-date", ".date"],
            blocked_paths=["/about", "/contact", "/privacy", "/cookies"],
        ),
    ),
    "us": ScraperSourceConfig(
        base_url="https://www.fsis.usda.gov",
        allowed_domains=["www.fsis.usda.gov", "fsis.usda.gov"],
        seed_urls=["https://www.fsis.usda.gov/recalls"],
        max_depth=2,
        max_pages_per_run=40,
        lookback_days=1,
        hints=ScraperHints(
            recall_keywords=["recall", "alert", "allergen", "salmonella", "listeria"],
            date_selectors=["time", ".date", ".recall-date"],
            blocked_paths=["/about-fsis", "/newsroom"],
            force_browser=False,
        ),
    ),
}

DEFAULT_SOURCE_NAMES: list[str] = list(SCRAPER_SOURCES)
