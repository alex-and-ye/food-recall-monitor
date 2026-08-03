"""Bootstrap homepage URLs for known official recall scrapers.

Homepage / listing entry URLs only. Full scraper config is discovered on
first use.
"""

from models.food_recall_alert import WebSource

# Mapping of bootstrap source name to listing/homepage URL
BOOTSTRAP_SCRAPER_SOURCES: dict[str, str] = {
    WebSource.FRANCE: "https://rappel.conso.gouv.fr/",
    WebSource.UK: "https://alerts.food.gov.uk/news-alerts",
    WebSource.GERMANY: "https://www.lebensmittelwarnung.de/DE/Home/home_node.html",
}

# Ordered list of bootstrap source names derived from BOOTSTRAP_SCRAPER_SOURCES
BOOTSTRAP_SOURCE_NAMES: list[str] = list(BOOTSTRAP_SCRAPER_SOURCES)
