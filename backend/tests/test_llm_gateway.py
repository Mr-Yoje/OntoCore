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
    assert "api_key" not in captured["kwargs"]
    assert "thinking" not in captured["kwargs"]


def test_lite_llm_passes_endpoint_key_and_thinking(monkeypatch):
    captured = _patch_litellm(monkeypatch, '{"ok": true}')
    gw = LiteLlmGateway(
        "openai/deepseek-chat",
        api_key="sk-live",
        api_base="https://api.deepseek.com/v1",
        thinking=True,
    )
    gw.complete_structured({"type": "object"}, [])
    kwargs = captured["kwargs"]
    assert kwargs["api_key"] == "sk-live"
    assert kwargs["api_base"] == "https://api.deepseek.com/v1"
    assert kwargs["reasoning_effort"] == "medium"
    assert kwargs["thinking"]["type"] == "enabled"
    assert kwargs["drop_params"] is True


def test_lite_llm_bad_json(monkeypatch):
    _patch_litellm(monkeypatch, "not-json")
    gw = LiteLlmGateway("openai/gpt-4o-mini")
    with pytest.raises(StructuredOutputError):
        gw.complete_structured({}, [])


def test_lite_llm_probe(monkeypatch):
    captured = _patch_litellm(monkeypatch, '{"ok": true}')
    gw = LiteLlmGateway("openai/deepseek-chat", api_key="sk-x", api_base="https://api.deepseek.com")
    assert gw.probe() == '{"ok": true}'
    assert captured["kwargs"]["timeout"] == 30
    assert captured["kwargs"]["max_tokens"] == 64


def test_lite_llm_empty_content(monkeypatch):
    _patch_litellm(monkeypatch, "")
    gw = LiteLlmGateway("openai/gpt-4o-mini")
    with pytest.raises(StructuredOutputError):
        gw.complete_structured({}, [])


def test_lite_llm_embed_parses_data_embeddings(monkeypatch):
    captured = {}

    def embedding(**kwargs):
        captured["kwargs"] = kwargs
        return SimpleNamespace(data=[{"embedding": [0.1, 0.2]}])

    monkeypatch.setitem(
        __import__("sys").modules,
        "litellm",
        SimpleNamespace(completion=lambda **k: None, embedding=embedding),
    )
    gw = LiteLlmGateway(
        "openai/text-embedding-3-small",
        api_key="sk-embed",
        api_base="https://api.example.com/v1",
    )
    assert gw.embed(["保险产品"]) == [[0.1, 0.2]]
    assert captured["kwargs"]["model"] == "openai/text-embedding-3-small"
    assert captured["kwargs"]["input"] == ["保险产品"]
    assert captured["kwargs"]["api_key"] == "sk-embed"
    assert captured["kwargs"]["api_base"] == "https://api.example.com/v1"
