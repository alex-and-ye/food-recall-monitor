from __future__ import annotations

import os

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
        hints=ScraperHints(
            detail_page_keywords=["/fiche-rappel/"],
            date_selectors=["time", ".date", "[datetime]"],
            blocked_paths=["/faq", "/mentions-legales", "/parametres"],
        ),
    ),
    "uk": ScraperSourceConfig(
        base_url="https://www.food.gov.uk",
        allowed_domains=["www.food.gov.uk", "food.gov.uk"],
        seed_urls=[
            "https://alerts.food.gov.uk/news-alerts",
        ],
        hints=ScraperHints(
            detail_page_keywords=["/news-alerts/alert/", "/recall/", "/alert/"],
            date_selectors=["time", ".published-date", ".date"],
            blocked_paths=["/about", "/contact", "/privacy", "/cookies"],
        ),
    ),
    "us": ScraperSourceConfig(
        base_url="https://www.fsis.usda.gov",
        allowed_domains=["www.fsis.usda.gov", "fsis.usda.gov"],
        seed_urls=["https://www.fsis.usda.gov/recalls"],
        request_headers={
            "Referer": "https://www.fsis.usda.gov/recalls",
            "Origin": "https://www.fsis.usda.gov",
        },
        proxy_url=os.getenv("FSIS_PROXY_URL"),
        hints=ScraperHints(
            detail_page_keywords=["/recalls-alerts/"],
            date_selectors=["time", ".date", ".recall-date"],
            blocked_paths=["/about-fsis", "/newsroom"],
            force_browser=True,
        ),
    ),
}

DEFAULT_SOURCE_NAMES: list[str] = list(SCRAPER_SOURCES)
