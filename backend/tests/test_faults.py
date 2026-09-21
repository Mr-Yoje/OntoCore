import json
from pathlib import Path

from fastapi.testclient import TestClient
from ontocore.api.app import create_app
from ontocore.extract.llm import LiteLlmGateway
from ontocore.faults import configure_logging, log_fault
from ontocore.jobs.service import JobService


def test_log_fault_writes_code_and_traceback(tmp_path):
    configure_logging(tmp_path)
    try:
        raise RuntimeError("upstream boom")
    except RuntimeError as exc:
        log_fault(code="OC-3101", kind="business", detail="抽取失败", request_id="req1", exc=exc)
    logs = list((Path(tmp_path) / "logs").glob("ontocore_*.log"))
    assert logs
    text = logs[0].read_text(encoding="utf-8")
    assert "OC-3101" in text
    assert "req1" in text
    assert "Traceback" in text
    assert "upstream boom" in text


def test_validation_error_has_code_kind_and_request_id(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path))
    response = client.post("/api/jobs", files={"file": ("a.txt", b"hi", "text/plain")})
    assert response.status_code == 400
    body = response.json()
    assert body["detail"] == "请选择供应商"
    assert "OC-" not in body["detail"]
    assert body["code"] == "OC-1101"
    assert body["kind"] == "business"
    assert body["request_id"]
    text = next((tmp_path / "logs").glob("ontocore_*.log")).read_text(encoding="utf-8")
    assert "OC-1101" in text


def test_unhandled_exception_is_system_500_and_logged(tmp_path, monkeypatch):
    def boom(self, job_id, filename, data):
        raise RuntimeError("disk exploded")

    monkeypatch.setattr(JobService, "run", boom)
    client = TestClient(create_app(data_dir=tmp_path), raise_server_exceptions=False)
    saved = client.put(
        "/api/settings",
        json={"providers": [{"label": "测", "prefix": "openai", "api_base": "", "api_key": "sk", "model": "fake"}]},
    ).json()["providers"][0]
    response = client.post(
        "/api/jobs",
        files={"file": ("a.txt", b"hi", "text/plain")},
        data={
            "provider_id": saved["id"],
            "model": "fake",
            "embed_model": "fake-embed",
            "embed_provider_id": saved["id"],
        },
    )
    assert response.status_code == 500
    body = response.json()
    assert body["code"] == "OC-9001"
    assert body["kind"] == "system"
    assert body["detail"] == "服务出错，请查看日志"
    assert "disk exploded" not in body["detail"]
    assert "Traceback" not in json.dumps(body)
    text = next((tmp_path / "logs").glob("ontocore_*.log")).read_text(encoding="utf-8")
    assert "Traceback" in text
    assert "disk exploded" in text
    assert "OC-9001" in text


def test_extract_failure_traceback_message_maps_to_public_error(tmp_path, monkeypatch):
    traceback_msg = (
        'Traceback (most recent call last):\n'
        '  File "litellm/main.py", line 1, in completion\n'
        'RuntimeError: provider exploded'
    )

    def boom(self, **kwargs):
        raise RuntimeError(traceback_msg)

    monkeypatch.setattr(LiteLlmGateway, "_call", boom)

    def factory(model, provider_id=None, thinking=False):
        return LiteLlmGateway("openai/fake")

    client = TestClient(create_app(data_dir=tmp_path, llm_factory=factory))
    saved = client.put(
        "/api/settings",
        json={"providers": [{"label": "测", "prefix": "openai", "api_base": "https://example.invalid", "api_key": "sk", "model": "fake"}]},
    ).json()["providers"][0]
    response = client.post(
        "/api/jobs",
        files={"file": ("a.txt", "标题\n\n正文。".encode("utf-8"), "text/plain")},
        data={
            "provider_id": saved["id"],
            "model": "fake",
            "embed_model": "fake-embed",
            "embed_provider_id": saved["id"],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["error"] == "模型调用失败"
    assert body["error_kind"] == "business"
    assert "Traceback" not in body["error"]
    assert "OC-" not in body["error"]
    text = next((tmp_path / "logs").glob("ontocore_*.log")).read_text(encoding="utf-8")
    assert "Traceback" in text
    assert "provider exploded" in text
    assert "OC-3101" in text


def test_extract_failure_logs_traceback_and_job_error_kind(tmp_path, monkeypatch):
    def boom(self, **kwargs):
        raise RuntimeError("upstream boom")

    monkeypatch.setattr(LiteLlmGateway, "_call", boom)

    def factory(model, provider_id=None, thinking=False):
        return LiteLlmGateway("openai/fake")

    client = TestClient(create_app(data_dir=tmp_path, llm_factory=factory))
    saved = client.put(
        "/api/settings",
        json={"providers": [{"label": "测", "prefix": "openai", "api_base": "https://example.invalid", "api_key": "sk", "model": "fake"}]},
    ).json()["providers"][0]
    response = client.post(
        "/api/jobs",
        files={"file": ("a.txt", "标题\n\n正文。".encode("utf-8"), "text/plain")},
        data={
            "provider_id": saved["id"],
            "model": "fake",
            "embed_model": "fake-embed",
            "embed_provider_id": saved["id"],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["error"]
    assert "OC-" not in body["error"]
    assert "Traceback" not in body["error"]
    assert body["error_kind"] == "business"
    text = next((tmp_path / "logs").glob("ontocore_*.log")).read_text(encoding="utf-8")
    assert "Traceback" in text
    assert "upstream boom" in text
    assert "OC-3101" in text


LITELLM_HTML_DUMP = (
    'litellm.InternalServerError: InternalServerError: OpenAIException - '
    'rel="icon" href="data:image/svg+xml;base64,PHN2ZyB4bWxucz0ia'
)


def test_public_llm_message_hides_litellm_html_dump():
    from ontocore.faults import public_llm_message

    mapped = public_llm_message(LITELLM_HTML_DUMP)
    assert mapped == "模型调用失败"
    assert "litellm" not in mapped.lower()
    assert "InternalServerError" not in mapped
    assert "rel=" not in mapped
    assert "data:image" not in mapped


def test_public_llm_message_hides_html_error_page():
    from ontocore.faults import public_llm_message

    raw = '<!DOCTYPE html><html><head><link rel="icon" href="data:image/svg+xml;base64,abc"></head></html>'
    assert public_llm_message(raw) == "模型调用失败"


def test_public_llm_message_keeps_mapped_and_chinese():
    from ontocore.faults import public_llm_message

    assert public_llm_message("401 Unauthorized") == "密钥无效或未填写，请检查 API Key"
    assert public_llm_message("模型列表为空") == "模型列表为空"


def test_settings_probe_hides_litellm_html_dump(tmp_path, monkeypatch):
    from types import SimpleNamespace

    def completion(**kwargs):
        raise RuntimeError(LITELLM_HTML_DUMP)

    monkeypatch.setitem(__import__("sys").modules, "litellm", SimpleNamespace(completion=completion))
    client = TestClient(create_app(data_dir=tmp_path))
    response = client.post(
        "/api/settings/test",
        json={
            "prefix": "openai",
            "model": "gpt-4o-mini",
            "api_base": "https://example.invalid/v1",
            "api_key": "sk-test",
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["detail"] == "模型调用失败"
    assert "OC-" not in body["detail"]
    dumped = json.dumps(body)
    assert "litellm" not in dumped
    assert "rel=" not in dumped
    assert "data:image" not in dumped
    text = next((tmp_path / "logs").glob("ontocore_*.log")).read_text(encoding="utf-8")
    assert "InternalServerError" in text or "OpenAIException" in text


def test_settings_models_hides_html_error_body(tmp_path, monkeypatch):
    import io
    import urllib.error

    html = b'<!DOCTYPE html><html><head><link rel="icon" href="data:image/svg+xml;base64,abc"></head></html>'

    def fake_urlopen(request, timeout=20):
        raise urllib.error.HTTPError(
            request.full_url, 500, "Internal Server Error", hdrs=None, fp=io.BytesIO(html)
        )

    monkeypatch.setattr("ontocore.settings.urllib.request.urlopen", fake_urlopen)
    client = TestClient(create_app(data_dir=tmp_path))
    response = client.post(
        "/api/settings/models",
        json={"api_base": "https://example.invalid", "api_key": "sk-test"},
    )
    assert response.status_code == 400
    body = response.json()
    assert body["detail"] == "模型调用失败"
    assert "rel=" not in body["detail"]
    assert "<!DOCTYPE" not in body["detail"]
    assert "data:image" not in json.dumps(body)

