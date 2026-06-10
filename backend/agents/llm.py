from __future__ import annotations

import json
from typing import Any

import ollama

from agents.config import DEFAULT_MODEL, OLLAMA_OPTIONS


class AgentOutputError(ValueError):
    pass


def chat_text(
    *,
    system_prompt: str,
    user_prompt: str,
    model: str = DEFAULT_MODEL,
) -> str:
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
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
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
