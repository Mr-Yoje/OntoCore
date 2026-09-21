from __future__ import annotations

import json
from typing import Protocol

from ontocore.errors import StructuredOutputError


class LlmGateway(Protocol):
    def complete_structured(self, schema: dict, messages: list[dict]) -> dict: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class FakeLlmGateway:
    def __init__(
        self,
        canned: dict | list[dict],
        *,
        embeddings: dict[str, list[float]] | None = None,
        fail_embed: bool = False,
    ) -> None:
        self._canned = canned
        self._embeddings = embeddings or {}
        self._fail_embed = fail_embed
        self.messages_log: list[list[dict]] = []

    def complete_structured(self, schema: dict, messages: list[dict]) -> dict:
        self.messages_log.append(messages)
        if isinstance(self._canned, list):
            if not self._canned:
                raise StructuredOutputError("fake gateway queue exhausted")
            item = self._canned.pop(0)
            if isinstance(item, dict) and item.get("__error__"):
                raise StructuredOutputError("fake gateway error")
            return item
        return self._canned

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self._fail_embed:
            raise StructuredOutputError("fake gateway embed failed")
        return [self._embeddings.get(text, [1.0, 0.0]) for text in texts]


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
            from ontocore.faults import log_fault, public_llm_message

            log_fault(code="OC-3101", kind="business", detail=public_llm_message(str(exc)), exc=exc)
            raise StructuredOutputError(public_llm_message(str(exc))) from exc

        content = response.choices[0].message.content
        if not content:
            raise StructuredOutputError("empty LLM response")
        return content

    def embed(self, texts: list[str]) -> list[list[float]]:
        import litellm

        try:
            response = litellm.embedding(
                model=self._model,
                input=texts,
                api_key=self._api_key or None,
                api_base=self._api_base or None,
            )
        except Exception as exc:
            from ontocore.faults import log_fault, public_llm_message

            log_fault(code="OC-3101", kind="business", detail=public_llm_message(str(exc)), exc=exc)
            raise StructuredOutputError(public_llm_message(str(exc))) from exc
        vectors: list[list[float]] = []
        for item in response.data:
            if isinstance(item, dict):
                vectors.append(item["embedding"])
            else:
                vectors.append(item.embedding)
        return vectors

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
