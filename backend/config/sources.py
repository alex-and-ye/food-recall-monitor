# Homepage / listing entry URLs only. Full scraper config is discovered on first use.
from models.food_recall_alert import WebSource

BOOTSTRAP_SCRAPER_SOURCES: dict[str, str] = {
    WebSource.FRANCE: "https://rappel.conso.gouv.fr/",
    WebSource.UK: "https://alerts.food.gov.uk/news-alerts",
    WebSource.GERMANY: "https://www.lebensmittelwarnung.de/DE/Home/home_node.html",
}

BOOTSTRAP_SOURCE_NAMES: list[str] = list(BOOTSTRAP_SCRAPER_SOURCES)
