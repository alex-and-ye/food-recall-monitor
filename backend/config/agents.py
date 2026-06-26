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
    "germany": ScraperSourceConfig(
        base_url="https://www.lebensmittelwarnung.de",
        allowed_domains=["www.lebensmittelwarnung.de", "lebensmittelwarnung.de"],
        seed_urls=["https://www.lebensmittelwarnung.de/DE/Home/home_node.html"],
        hints=ScraperHints(
            detail_page_keywords=["/___lebensmittelwarnung.de/"],
            date_selectors=["time", ".date", "[datetime]"],
            blocked_paths=["/DE/Service", "/DE/FAQ", "/DE/Glossar", "/DE/Themen"],
        ),
    ),
}

DEFAULT_SOURCE_NAMES: list[str] = list(SCRAPER_SOURCES)
