from __future__ import annotations

from typing import Any

ApiSourceConfig = str | dict[str, Any]

TRANSLATION_MODEL: str = "qwen2.5:14b"
SUMMARIZATION_MODEL: str = "qwen2.5:14b"
STRUCTURING_MODEL: str = "qwen2.5:14b"

OLLAMA_OPTIONS: dict[str, float | int] = {
    "temperature": 0.0,
    "num_ctx": 4096,
    "num_gpu": 99,
}

API_SOURCES: dict[str, ApiSourceConfig] = {
    "france": 'https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets/rappelconso-v2-gtin-espaces/records?where=categorie_produit%3D"alimentation"&order_by=date_publication%20desc',
    "uk": "https://data.food.gov.uk/food-alerts/id?_view=full&_limit=100&_sort=-created",
    "us": {
        "url": "https://www.fsis.usda.gov/fsis/api/recall/v/1?field_translation_language=es",
        "headers": {
            "Referer": "https://www.fsis.usda.gov/recalls",
            "Origin": "https://www.fsis.usda.gov",
        },
    },
}

DEFAULT_SOURCE_NAMES: list[str] = list(API_SOURCES)
