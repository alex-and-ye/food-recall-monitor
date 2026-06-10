DEFAULT_MODEL = "qwen2.5:14b"

OLLAMA_OPTIONS = {
    "temperature": 0.0,
    "num_ctx": 4096,
    "num_gpu": 99,
}

API_SOURCES = {
    "france": 'https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets/rappelconso-v2-gtin-espaces/records?where=categorie_produit%3D"alimentation"&order_by=date_publication%20desc',
    "uk": "https://data.food.gov.uk/food-alerts/id?_view=full&_limit=100&_sort=-created",
    "us": "https://www.fsis.usda.gov/fsis/api/recall/v/1?field_translation_language=es",
}

DEFAULT_SOURCE_NAMES = list(API_SOURCES)
