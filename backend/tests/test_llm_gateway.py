from types import SimpleNamespace

import pytest

from ontocore.errors import StructuredOutputError
from ontocore.extract.llm import FakeLlmGateway, LiteLlmGateway


def test_fake_returns_canned():
    gw = FakeLlmGateway({"objects": []})
    assert gw.complete_structured({}, []) == {"objects": []}


def _patch_litellm(monkeypatch, content):
    captured = {}

    def completion(**kwargs):
        captured["kwargs"] = kwargs
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    monkeypatch.setitem(__import__("sys").modules, "litellm", SimpleNamespace(completion=completion))
    return captured


def test_lite_llm_prefers_json_object(monkeypatch):
    captured = _patch_litellm(monkeypatch, '{"ok": true}')
    gw = LiteLlmGateway("openai/gpt-4o-mini")
    assert gw.complete_structured({"type": "object"}, [{"role": "user", "content": "x"}]) == {"ok": True}
    assert captured["kwargs"]["response_format"] == {"type": "json_object"}
    assert captured["kwargs"]["model"] == "openai/gpt-4o-mini"


def test_lite_llm_bad_json(monkeypatch):
    _patch_litellm(monkeypatch, "not-json")
    gw = LiteLlmGateway("openai/gpt-4o-mini")
    with pytest.raises(StructuredOutputError):
        gw.complete_structured({}, [])


def test_lite_llm_empty_content(monkeypatch):
    _patch_litellm(monkeypatch, "")
    gw = LiteLlmGateway("openai/gpt-4o-mini")
    with pytest.raises(StructuredOutputError):
        gw.complete_structured({}, [])
