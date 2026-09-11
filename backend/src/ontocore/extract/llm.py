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
    def __init__(
        self,
        model: str,
        *,
        api_key: str = "",
        api_base: str = "",
        thinking: bool = False,
    ) -> None:
        self._model = model
        self._api_key = api_key.strip()
        self._api_base = api_base.strip()
        self._thinking = thinking

    def _call(self, *, messages: list[dict], extra: dict | None = None) -> str:
        import litellm

        kwargs: dict = {
            "model": self._model,
            "messages": messages,
            "drop_params": True,
        }
        if self._api_key:
            kwargs["api_key"] = self._api_key
        if self._api_base:
            kwargs["api_base"] = self._api_base
        if self._thinking:
            kwargs["reasoning_effort"] = "medium"
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": 2048}
        if extra:
            kwargs.update(extra)

        try:
            response = litellm.completion(**kwargs)
        except Exception as exc:
            raise StructuredOutputError(str(exc)) from exc

        content = response.choices[0].message.content
        if not content:
            raise StructuredOutputError("empty LLM response")
        return content

    def complete_structured(self, schema: dict, messages: list[dict]) -> dict:
        content = self._call(
            messages=messages,
            extra={"response_format": {"type": "json_object"}},
        )
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise StructuredOutputError("invalid JSON in LLM response") from exc

        if not isinstance(parsed, dict):
            raise StructuredOutputError("LLM response is not a JSON object")

        return parsed

    def probe(self) -> str:
        content = self._call(
            messages=[
                {
                    "role": "user",
                    "content": 'Reply with JSON {"ok": true} and nothing else.',
                }
            ],
            extra={
                "response_format": {"type": "json_object"},
                "max_tokens": 64,
                "timeout": 30,
            },
        )
        return content.strip()[:200]
