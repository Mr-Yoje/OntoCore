from __future__ import annotations

import json
from typing import Protocol

from ontocore.errors import StructuredOutputError


class LlmGateway(Protocol):
    def complete_structured(self, schema: dict, messages: list[dict]) -> dict: ...


class FakeLlmGateway:
    def __init__(self, canned: dict) -> None:
        self._canned = canned

    def complete_structured(self, schema: dict, messages: list[dict]) -> dict:
        return self._canned


class LiteLlmGateway:
    def __init__(self, model: str) -> None:
        self._model = model

    def complete_structured(self, schema: dict, messages: list[dict]) -> dict:
        import litellm

        kwargs: dict = {
            "model": self._model,
            "messages": messages,
            "response_format": {"type": "json_object"},
        }

        try:
            response = litellm.completion(**kwargs)
        except Exception as exc:
            raise StructuredOutputError(str(exc)) from exc

        content = response.choices[0].message.content
        if not content:
            raise StructuredOutputError("empty LLM response")

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise StructuredOutputError("invalid JSON in LLM response") from exc

        if not isinstance(parsed, dict):
            raise StructuredOutputError("LLM response is not a JSON object")

        return parsed
