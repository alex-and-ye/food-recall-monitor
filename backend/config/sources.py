from __future__ import annotations

# Homepage / listing entry URLs only. Full scraper config is discovered on first use.
BOOTSTRAP_SCRAPER_SOURCES: dict[str, str] = {
    "france": "https://rappel.conso.gouv.fr/",
    "uk": "https://alerts.food.gov.uk/news-alerts",
    "germany": "https://www.lebensmittelwarnung.de/DE/Home/home_node.html",
}

BOOTSTRAP_SOURCE_NAMES: list[str] = list(BOOTSTRAP_SCRAPER_SOURCES)
