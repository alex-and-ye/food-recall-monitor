from __future__ import annotations

TRANSLATION_MODEL: str = "qwen2.5:14b"
SUMMARIZATION_MODEL: str = "qwen2.5:14b"
STRUCTURING_MODEL: str = "qwen2.5:14b"
CLASSIFICATION_MODEL: str = "qwen2.5:14b"

OLLAMA_OPTIONS: dict[str, float | int] = {
    "temperature": 0.0,
    "num_ctx": 4096,
    "num_gpu": 99,
}

# Homepage / listing entry URLs only. Full scraper config is discovered on first use.
BOOTSTRAP_SCRAPER_SOURCES: dict[str, str] = {
    "france": "https://rappel.conso.gouv.fr/",
    "uk": "https://alerts.food.gov.uk/news-alerts",
    "germany": "https://www.lebensmittelwarnung.de/DE/Home/home_node.html",
}

BOOTSTRAP_SOURCE_NAMES: list[str] = list(BOOTSTRAP_SCRAPER_SOURCES)
