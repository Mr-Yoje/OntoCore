import json
from pathlib import Path

from fastapi.testclient import TestClient
from ontocore.api.app import create_app
from ontocore.extract.llm import LiteLlmGateway
from ontocore.faults import configure_logging, log_fault
from ontocore.jobs.runner import JobRunner
from ontocore.jobs.service import JobService


def _sync_app(**kwargs):
    kwargs.setdefault("job_runner", JobRunner(sync=True))
    return create_app(**kwargs)

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
    client = TestClient(_sync_app(data_dir=tmp_path), raise_server_exceptions=False)
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
    assert response.status_code == 200
    assert response.json()["status"] == "queued"
    response = client.post(f"/api/jobs/{response.json()['id']}/start")
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

    client = TestClient(_sync_app(data_dir=tmp_path, llm_factory=factory))
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
    assert response.json()["status"] == "queued"
    response = client.post(f"/api/jobs/{response.json()['id']}/start")
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

    client = TestClient(_sync_app(data_dir=tmp_path, llm_factory=factory))
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
    assert response.json()["status"] == "queued"
    response = client.post(f"/api/jobs/{response.json()['id']}/start")
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


def test_map_provider_fault_settings_and_job():
    from ontocore.faults import map_provider_fault, public_llm_message
    from ontocore.error_catalog import fault_detail

    assert map_provider_fault("401 Unauthorized", domain="settings") == "OC-5004"
    assert map_provider_fault("401 Unauthorized", domain="job") == "OC-3102"
    assert map_provider_fault("[Errno 11001] getaddrinfo failed", domain="settings") == "OC-5006"
    assert map_provider_fault("timed out", domain="job") == "OC-3104"
    assert map_provider_fault("litellm.InternalServerError", domain="settings") == "OC-5009"
    assert public_llm_message("401 Unauthorized", domain="job") == fault_detail("OC-3102")


def test_llm_gateway_maps_401_to_oc_3102(monkeypatch):
    from types import SimpleNamespace

    from ontocore.errors import StructuredOutputError
    from ontocore.extract.llm import LiteLlmGateway

    def boom(**kwargs):
        raise RuntimeError("401 Unauthorized")

    monkeypatch.setitem(__import__("sys").modules, "litellm", SimpleNamespace(completion=boom))
    gw = LiteLlmGateway(model="m", api_base="https://x", api_key="sk")
    try:
        gw.complete_structured({"type": "object"}, [{"role": "user", "content": "hi"}])
        assert False, "expected error"
    except StructuredOutputError as exc:
        assert exc.code == "OC-3102"
        assert str(exc) == "密钥无效或未填写，请检查 API Key"


def test_business_error_detail_comes_from_catalog():
    from ontocore.errors import BusinessError
    from ontocore.error_catalog import fault_detail

    exc = BusinessError("会被覆盖的手写文案", code="OC-5001")
    assert exc.code == "OC-5001"
    assert exc.message == fault_detail("OC-5001")
    assert str(exc) == fault_detail("OC-5001")
    assert exc.kind == "business"
    assert exc.http_status == 400


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
    from ontocore.error_catalog import fault_detail

    assert public_llm_message("401 Unauthorized") == fault_detail("OC-5004")
    assert public_llm_message("模型列表为空") == fault_detail("OC-5009")


def test_public_llm_message_maps_offline_dns():
    from ontocore.faults import public_llm_message
    from ontocore.error_catalog import fault_detail

    mapped = public_llm_message("[Errno 11001] getaddrinfo failed")
    assert mapped == fault_detail("OC-5006")
    assert "getaddrinfo" not in mapped
    assert public_llm_message("Network is unreachable") == fault_detail("OC-5006")


def test_settings_probe_hides_litellm_html_dump(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from ontocore.error_catalog import fault_detail

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
    assert body["code"] == "OC-5009"
    assert body["detail"] == fault_detail("OC-5009")
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

    from ontocore.error_catalog import fault_detail

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
    assert body["code"] == "OC-5009"
    assert body["detail"] == fault_detail("OC-5009")
    assert "rel=" not in body["detail"]
    assert "<!DOCTYPE" not in body["detail"]
    assert "data:image" not in json.dumps(body)


def test_settings_models_missing_base_uses_oc_5001(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path))
    response = client.post("/api/settings/models", json={"api_base": "", "api_key": "sk"})
    assert response.status_code == 400
    assert response.json()["code"] == "OC-5001"
    assert response.json()["detail"] == "请填写 Base URL"


def test_settings_models_maps_offline_to_oc_5006(tmp_path, monkeypatch):
    import urllib.error

    def fake_urlopen(request, timeout=20):
        raise urllib.error.URLError("[Errno 11001] getaddrinfo failed")

    monkeypatch.setattr("ontocore.settings.urllib.request.urlopen", fake_urlopen)
    client = TestClient(create_app(data_dir=tmp_path))
    response = client.post(
        "/api/settings/models",
        json={"api_base": "https://api.openai.com", "api_key": "sk-test"},
    )
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "OC-5006"
    assert body["detail"] == "无法连接服务，请检查网络"


EXPECTED_FAULTS = {
    "OC-1101": ("business", 400, "请选择供应商"),
    "OC-1102": ("business", 400, "请选择抽取模型"),
    "OC-1103": ("business", 400, "请选择嵌入模型"),
    "OC-1104": ("business", 400, "请选择嵌入供应商"),
    "OC-1105": ("business", 400, "未找到所选供应商，请先在设置中添加"),
    "OC-1106": ("business", 400, "未找到所选嵌入供应商，请先在设置中添加"),
    "OC-1107": ("business", 400, "当前状态不能启动抽取"),
    "OC-1108": ("business", 400, "上传文件已丢失，请重新新建作业"),
    "OC-1109": ("business", 400, "当前状态不能修改作业"),
    "OC-1004": ("business", 404, "未找到"),
    "OC-2001": ("business", 400, "不符合对象关系约束"),
    "OC-2002": ("business", 400, "无法写入对象、属性或关系"),
    "OC-2003": ("business", 409, "与已有数据冲突"),
    "OC-2004": ("business", 409, "仍有实例占用该对象"),
    "OC-2005": ("business", 409, "仍有实例占用该属性"),
    "OC-2006": ("business", 409, "仍有实例占用该关系"),
    "OC-2007": ("business", 400, "请选择要对齐的已有对象或关系"),
    "OC-3001": ("business", 400, "无法提取文本"),
    "OC-3101": ("business", 400, "模型调用失败"),
    "OC-3102": ("business", 400, "密钥无效或未填写，请检查 API Key"),
    "OC-3103": ("business", 400, "判重失败"),
    "OC-3104": ("business", 400, "连接超时，请检查 Base URL 或网络"),
    "OC-3105": ("business", 400, "无法连接服务，请检查网络"),
    "OC-3106": ("business", 400, "接口不存在，请检查 Base URL 和模型名称"),
    "OC-3107": ("business", 400, "请求过于频繁，请稍后再试"),
    "OC-3108": ("business", 400, "服务已重启，请重新抽取"),
    "OC-4001": ("system", 503, "图不可用"),
    "OC-5001": ("business", 400, "请填写 Base URL"),
    "OC-5002": ("business", 400, "请填写 API Key"),
    "OC-5003": ("business", 400, "请选择具体模型"),
    "OC-5004": ("business", 400, "密钥无效或未填写，请检查 API Key"),
    "OC-5005": ("business", 400, "连接超时，请检查 Base URL 或网络"),
    "OC-5006": ("business", 400, "无法连接服务，请检查网络"),
    "OC-5007": ("business", 400, "接口不存在，请检查 Base URL 和模型名称"),
    "OC-5008": ("business", 400, "请求过于频繁，请稍后再试"),
    "OC-5009": ("business", 400, "模型调用失败"),
    "OC-9001": ("system", 500, "服务出错，请查看日志"),
}


def test_error_catalog_matches_spec():
    from ontocore.error_catalog import FAULTS, fault_detail

    assert set(FAULTS) == set(EXPECTED_FAULTS)
    for code, (kind, status, detail) in EXPECTED_FAULTS.items():
        entry = FAULTS[code]
        assert entry["kind"] == kind
        assert entry["http_status"] == status
        assert entry["detail"] == detail
        assert fault_detail(code) == detail
        assert "OC-" not in detail
