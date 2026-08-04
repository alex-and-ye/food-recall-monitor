"""Ollama model names and generation options for agent LLM calls.

Used by translation, summarization, structuring, and classification agents.
"""

# Ollama model for translating recall text into English
TRANSLATION_MODEL: str = "qwen2.5:14b"
# Ollama model for summarizing recall content
SUMMARIZATION_MODEL: str = "qwen2.5:14b"
# Ollama model for extracting structured alert fields
STRUCTURING_MODEL: str = "qwen2.5:14b"
# Ollama model for risk / hazard classification
CLASSIFICATION_MODEL: str = "qwen2.5:14b"

# Shared Ollama sampling and context options for agent inference
OLLAMA_OPTIONS: dict[str, float | int] = {
    "temperature": 0.0,
    "num_ctx": 4096,
    "num_gpu": 99,
}
