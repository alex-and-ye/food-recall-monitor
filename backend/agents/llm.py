"""Ollama chat helpers for agent pipeline LLM steps.

Wraps structured JSON and plain-text chat calls used by translation,
summarization, and structuring nodes.
"""

import json
from typing import Any

import ollama

from config.agents import OLLAMA_OPTIONS, STRUCTURING_MODEL, SUMMARIZATION_MODEL


class AgentOutputError(ValueError):
    """Raised when an LLM response cannot be parsed or does not match expectations."""


def chat_text(
    *,
    system_prompt: str,
    user_prompt: str,
    model: str = SUMMARIZATION_MODEL,
) -> str:
    """Send a chat request and return the model's plain-text reply.

    Args:
        system_prompt: System message defining agent behavior and output rules.
        user_prompt: User message containing input data for the agent.
        model: Ollama model identifier. Defaults to the summarization model.

    Returns:
        Trimmed text content from the model response.
    """
    response = ollama.chat(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        options=OLLAMA_OPTIONS,
    )
    return str(response["message"]["content"]).strip()


def chat_json(
    *,
    system_prompt: str,
    user_prompt: str,
    model: str = STRUCTURING_MODEL,
) -> dict[str, Any]:
    """Send a chat request and parse the reply as a JSON object.

    Args:
        system_prompt: System message defining agent behavior and JSON schema.
        user_prompt: User message containing input data for the agent.
        model: Ollama model identifier. Defaults to the structuring model.

    Returns:
        Parsed JSON object from the model response.

    Raises:
        AgentOutputError: If the response is not valid JSON or is not an object.
    """
    raw_text = str(ollama.chat(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        options=OLLAMA_OPTIONS,
        format="json",
    )["message"]["content"])

    try:
        parsed = _parse_json_object(raw_text)
    except json.JSONDecodeError as exc:
        raise AgentOutputError("Agent returned invalid JSON") from exc

    if not isinstance(parsed, dict):
        raise AgentOutputError("Agent JSON response must be an object")

    return parsed


def _parse_json_object(raw_text: str) -> Any:
    """Parse JSON from raw text, tolerating leading non-JSON content."""
    text = raw_text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        object_start = text.find("{")
        if object_start == -1:
            raise

        decoder = json.JSONDecoder()
        parsed, _ = decoder.raw_decode(text[object_start:])
        return parsed
