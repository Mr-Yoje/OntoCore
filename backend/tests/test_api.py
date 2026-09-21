import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from ontocore.api.app import create_app
from ontocore.constants import NS
from ontocore.errors import GraphUnavailable
from ontocore.graph.ports import GraphNode
from ontocore.ontology.repository import OntologyRepository


def test_empty_network_and_no_domain_pack_routes():
    client = TestClient(create_app())
    r = client.get("/api/ontology/network")
    assert r.status_code == 200
    assert r.json()["nodes"] == []
    paths = {getattr(route, "path", "") for route in client.app.routes}
    assert not any("domain" in p for p in paths)
    created = client.post("/api/objects", json={"local_name": "Product", "label": "保险产品", "definition": "一种产品"})
    assert created.status_code == 200
    net = client.get("/api/ontology/network").json()
    assert net["nodes"][0]["label"] == "保险产品"


def test_create_app_does_not_load_seed_turtle(monkeypatch):
    def boom(self, *args, **kwargs):
        raise AssertionError("create_app must not import Turtle")

    monkeypatch.setattr(OntologyRepository, "import_turtle", boom)
    client = TestClient(create_app())
    assert client.get("/api/ontology/network").status_code == 200


def test_openapi_uses_product_language():
    spec = json.dumps(TestClient(create_app()).get("/openapi.json").json(), ensure_ascii=False)
    assert "领域包" not in spec
    assert "TBox" not in spec
    assert "类" not in spec


def test_settings_stores_providers_not_extractor(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path))
    body = client.get("/api/settings").json()
    assert body == {"providers": []}
    updated = client.put(
        "/api/settings",
        json={
            "providers": [
                {
                    "label": "DeepSeek",
                    "prefix": "openai",
                    "api_base": "https://api.deepseek.com",
                    "api_key": "sk-test",
                }
            ]
        },
    )
    assert updated.status_code == 200
    saved = updated.json()["providers"]
    assert len(saved) == 1
    assert saved[0]["label"] == "DeepSeek"
    assert saved[0]["has_api_key"] is True
    assert "api_key" not in saved[0]
    assert "extractor" not in updated.json()
    disk = (tmp_path / "ontocore.db").read_bytes()
    assert b"sk-test" not in disk
    if (tmp_path / "settings.json").exists():
        assert "sk-test" not in (tmp_path / "settings.json").read_text(encoding="utf-8")
    kept = client.put(
        "/api/settings",
        json={
            "providers": [
                {
                    "id": saved[0]["id"],
                    "label": "DeepSeek",
                    "prefix": "openai",
                    "api_base": "https://api.deepseek.com",
                    "api_key": None,
                }
            ]
        },
    )
    assert kept.json()["providers"][0]["has_api_key"] is True
    assert "api_key" not in kept.json()["providers"][0]
    assert client.get("/api/settings").json()["providers"][0]["has_api_key"] is True


def test_settings_lists_litellm_prefixes():
    client = TestClient(create_app())
    response = client.get("/api/settings/prefixes")
    assert response.status_code == 200
    prefixes = response.json()["prefixes"]
    assert prefixes == sorted(set(prefixes))
    for name in ("openai", "deepseek", "anthropic", "dashscope"):
        assert name in prefixes


def test_settings_stores_selected_model(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path))
    updated = client.put(
        "/api/settings",
        json={
            "providers": [
                {
                    "label": "DeepSeek",
                    "prefix": "openai",
                    "api_base": "https://api.deepseek.com",
                    "api_key": "sk-test",
                    "model": "deepseek-chat",
                }
            ]
        },
    )
    assert updated.status_code == 200
    assert updated.json()["providers"][0]["model"] == "deepseek-chat"
    assert client.get("/api/settings").json()["providers"][0]["model"] == "deepseek-chat"


def test_settings_migrates_legacy_file(tmp_path):
    (tmp_path / "settings.json").write_text(
        json.dumps(
            {
                "extractor": "hybrid",
                "model": "openai/deepseek-chat",
                "api_base": "https://api.deepseek.com",
                "api_key": "sk-old",
                "thinking": True,
            }
        ),
        encoding="utf-8",
    )
    client = TestClient(create_app(data_dir=tmp_path))
    providers = client.get("/api/settings").json()["providers"]
    assert providers[0]["label"] == "默认供应商"
    assert providers[0]["prefix"] == "openai"
    assert providers[0]["has_api_key"] is True
    assert "api_key" not in providers[0]
    assert "sk-old" not in (tmp_path / "ontocore.db").read_bytes().decode("latin-1", errors="ignore")
    leftover = (tmp_path / "settings.json").read_text(encoding="utf-8") if (tmp_path / "settings.json").exists() else ""
    assert "sk-old" not in leftover


def test_settings_probe_ok(tmp_path, monkeypatch):
    captured = {}

    def completion(**kwargs):
        captured["kwargs"] = kwargs
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))])

    monkeypatch.setitem(__import__("sys").modules, "litellm", SimpleNamespace(completion=completion))
    client = TestClient(create_app(data_dir=tmp_path))
    r = client.post(
        "/api/settings/test",
        json={
            "prefix": "openai",
            "model": "deepseek-chat",
            "api_base": "https://api.deepseek.com",
            "api_key": "sk-test",
            "thinking": False,
        },
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["model"] == "openai/deepseek-chat"
    assert captured["kwargs"]["api_base"] == "https://api.deepseek.com"
    assert captured["kwargs"]["model"] == "openai/deepseek-chat"
    assert captured["kwargs"]["timeout"] == 30


def test_settings_probe_uses_saved_key(tmp_path, monkeypatch):
    def completion(**kwargs):
        if kwargs.get("api_key") != "sk-saved":
            raise RuntimeError("missing key")
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))])

    monkeypatch.setitem(__import__("sys").modules, "litellm", SimpleNamespace(completion=completion))
    client = TestClient(create_app(data_dir=tmp_path))
    created = client.put(
        "/api/settings",
        json={
            "providers": [
                {"label": "DeepSeek", "prefix": "openai", "api_base": "https://api.deepseek.com", "api_key": "sk-saved"}
            ]
        },
    ).json()["providers"][0]
    r = client.post(
        "/api/settings/test",
        json={"provider_id": created["id"], "model": "deepseek-chat", "api_key": None},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_settings_lists_models_from_provider(tmp_path, monkeypatch):
    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"data": [{"id": "deepseek-chat"}, {"id": "deepseek-reasoner"}]}).encode()

    def fake_urlopen(request, timeout=20):
        assert request.full_url == "https://api.deepseek.com/v1/models"
        assert request.get_header("Authorization") == "Bearer sk-list"
        return FakeResp()

    monkeypatch.setattr("ontocore.settings.urllib.request.urlopen", fake_urlopen)
    client = TestClient(create_app(data_dir=tmp_path))
    r = client.post(
        "/api/settings/models",
        json={"api_base": "https://api.deepseek.com", "api_key": "sk-list"},
    )
    assert r.status_code == 200
    assert r.json()["models"] == ["deepseek-chat", "deepseek-reasoner"]


def test_settings_lists_models_uses_saved_key(tmp_path, monkeypatch):
    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"data": [{"id": "deepseek-chat"}]}).encode()

    def fake_urlopen(request, timeout=20):
        assert request.get_header("Authorization") == "Bearer sk-saved"
        return FakeResp()

    monkeypatch.setattr("ontocore.settings.urllib.request.urlopen", fake_urlopen)
    client = TestClient(create_app(data_dir=tmp_path))
    created = client.put(
        "/api/settings",
        json={
            "providers": [
                {"label": "DeepSeek", "prefix": "openai", "api_base": "https://api.deepseek.com", "api_key": "sk-saved"}
            ]
        },
    ).json()["providers"][0]
    r = client.post("/api/settings/models", json={"provider_id": created["id"], "api_key": None})
    assert r.status_code == 200
    assert r.json()["models"] == ["deepseek-chat"]


def test_settings_probe_error(tmp_path, monkeypatch):
    def completion(**kwargs):
        raise RuntimeError("401 Unauthorized")

    monkeypatch.setitem(__import__("sys").modules, "litellm", SimpleNamespace(completion=completion))
    client = TestClient(create_app(data_dir=tmp_path))
    r = client.post(
        "/api/settings/test",
        json={"prefix": "openai", "model": "deepseek-chat", "api_key": "bad"},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "密钥无效或未填写，请检查 API Key"


def test_duplicate_object_is_ontology_write_400():
    client = TestClient(create_app())
    payload = {"local_name": "Product", "label": "保险产品", "definition": "一种产品"}
    assert client.post("/api/objects", json=payload).status_code == 200
    r = client.post("/api/objects", json=payload)
    assert r.status_code == 400
    text = r.text
    assert "对象" in text
    assert "类" not in text


def test_delete_object_conflicts_when_instances_exist():
    app = create_app()
    client = TestClient(app)
    client.post("/api/objects", json={"local_name": "Product", "label": "保险产品", "definition": "一种产品"})
    app.state.graph.upsert_node(
        GraphNode(
            onto_iri=f"{NS}p1",
            type_iri=f"{NS}Product",
            onto_label="保险产品",
            evidence="e",
            block_id="b0",
            data={},
        )
    )
    r = client.delete("/api/objects/Product")
    assert r.status_code == 409
    assert "实例" in r.json()["detail"]
    assert "对象" in r.json()["detail"]


@pytest.mark.parametrize(
    "filename,content",
    [
        ("empty.txt", b""),
        ("upload.bin", b"binary"),
    ],
)
def test_post_jobs_ingress_error_returns_400(filename, content):
    client = TestClient(create_app())
    r = client.post("/api/jobs", files={"file": (filename, content, "application/octet-stream")})
    assert r.status_code == 400
    assert r.json()["detail"]


def test_graph_unavailable_is_503():
    class DownGraph:
        def instance_network(self, type_iri=None):
            raise GraphUnavailable("down")

    client = TestClient(create_app(graph=DownGraph()))
    r = client.get("/api/graph/network")
    assert r.status_code == 503
    assert "图不可用" in r.json()["detail"]


def test_get_object_attributes_includes_inherited():
    client = TestClient(create_app())
    client.post("/api/objects", json={"local_name": "Product", "label": "保险产品", "definition": "一种产品"})
    client.post(
        "/api/objects/Product/attributes",
        json={"local_name": "name", "label": "名称", "definition": "显示名", "literal_kind": "text"},
    )
    client.post(
        "/api/objects",
        json={"local_name": "Critical", "label": "重疾险", "definition": "d", "parent_local_name": "Product"},
    )
    r = client.get("/api/objects/Critical/attributes")
    assert r.status_code == 200
    assert {item["label"] for item in r.json()} == {"名称"}


def test_create_app_data_dir_from_env(tmp_path, monkeypatch):
    target = tmp_path / "onto-data"
    monkeypatch.setenv("ONTOCORE_DATA_DIR", str(target))
    app = create_app()
    assert Path(app.state.data_dir) == target


def test_create_app_default_data_dir_is_cwd_data(tmp_path, monkeypatch):
    monkeypatch.delenv("ONTOCORE_DATA_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    app = create_app()
    assert Path(app.state.data_dir).resolve() == (tmp_path / "data").resolve()


def test_post_jobs_extractor_error_is_not_500(tmp_path, monkeypatch):
    class Boom:
        def extract(self, *args, **kwargs):
            raise RuntimeError("llm down")

    monkeypatch.setattr("ontocore.jobs.service.get_extractor", lambda name: Boom())
    client = TestClient(create_app(data_dir=tmp_path))
    saved = client.put(
        "/api/settings",
        json={
            "providers": [
                {
                    "label": "测试供应商",
                    "prefix": "openai",
                    "api_base": "",
                    "api_key": "sk-test",
                    "model": "fake",
                }
            ]
        },
    ).json()["providers"][0]
    r = client.post(
        "/api/jobs",
        files={"file": ("a.txt", "标题\n\n正文。".encode("utf-8"), "text/plain")},
        data={"provider_id": saved["id"], "model": "fake", "embed_model": "fake-embed", "embed_provider_id": saved["id"]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "failed"
    assert body["error"] == "抽取失败"
    assert "OC-" not in body["error"]
    text = next((tmp_path / "logs").glob("ontocore_*.log")).read_text(encoding="utf-8")
    assert "llm down" in text
    assert "Traceback" in text


def test_create_job_requires_provider_and_stores_guides(tmp_path, monkeypatch):
    from ontocore.jobs.service import JobService

    monkeypatch.setattr(
        JobService,
        "run",
        lambda self, job_id, filename, data: self._jobs.set_status(job_id, "completed"),
    )
    client = TestClient(create_app(data_dir=tmp_path))
    client.put(
        "/api/settings",
        json={
            "providers": [
                {
                    "label": "DeepSeek",
                    "prefix": "deepseek",
                    "api_base": "https://api.deepseek.com",
                    "api_key": "sk",
                    "model": "deepseek-chat",
                }
            ]
        },
    )
    pid = client.get("/api/settings").json()["providers"][0]["id"]
    missing = client.post("/api/jobs", files={"file": ("a.txt", b"hi", "text/plain")})
    assert missing.status_code == 400
    no_embed = client.post(
        "/api/jobs",
        files={"file": ("a.txt", b"hi", "text/plain")},
        data={"provider_id": pid, "model": "deepseek-chat"},
    )
    assert no_embed.status_code == 400
    assert "嵌入" in no_embed.json()["detail"]
    r = client.post(
        "/api/jobs",
        files={"file": ("a.txt", b"hi", "text/plain")},
        data={
            "provider_id": pid,
            "model": "deepseek-chat",
            "embed_model": "embed-x",
            "embed_provider_id": pid,
            "guide_object_iris": "https://ontocore.local/ns/working#Product",
        },
    )
    assert r.status_code == 200
    assert r.json()["extractor"] == "llm"
    assert r.json()["embed_model"] == "embed-x"
    assert r.json()["embed_provider_id"] == pid
    assert "https://ontocore.local/ns/working#Product" in r.json()["guide_object_iris"]


def test_create_job_uses_separate_embed_provider(tmp_path, monkeypatch):
    from ontocore.jobs.service import JobService

    monkeypatch.setattr(
        JobService,
        "run",
        lambda self, job_id, filename, data: self._jobs.set_status(job_id, "completed"),
    )
    client = TestClient(create_app(data_dir=tmp_path))
    saved = client.put(
        "/api/settings",
        json={
            "providers": [
                {
                    "label": "抽取供应商",
                    "prefix": "openai",
                    "api_base": "https://api.example.com",
                    "api_key": "sk-chat",
                    "model": "chat",
                },
                {
                    "label": "嵌入供应商",
                    "prefix": "dashscope",
                    "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                    "api_key": "sk-embed",
                    "model": "embed",
                },
            ]
        },
    ).json()["providers"]
    chat_id, embed_id = saved[0]["id"], saved[1]["id"]
    missing = client.post(
        "/api/jobs",
        files={"file": ("a.txt", b"hi", "text/plain")},
        data={
            "provider_id": chat_id,
            "model": "chat",
            "embed_model": "embed-x",
        },
    )
    assert missing.status_code == 400
    assert "嵌入" in missing.json()["detail"]
    unknown = client.post(
        "/api/jobs",
        files={"file": ("a.txt", b"hi", "text/plain")},
        data={
            "provider_id": chat_id,
            "model": "chat",
            "embed_model": "embed-x",
            "embed_provider_id": "missing",
        },
    )
    assert unknown.status_code == 400
    r = client.post(
        "/api/jobs",
        files={"file": ("a.txt", b"hi", "text/plain")},
        data={
            "provider_id": chat_id,
            "model": "chat",
            "embed_model": "embed-x",
            "embed_provider_id": embed_id,
        },
    )
    assert r.status_code == 200
    assert r.json()["provider_id"] == chat_id
    assert r.json()["embed_provider_id"] == embed_id
    assert r.json()["embed_model"] == "embed-x"


def test_accept_type_candidate_forwards_json_mode(tmp_path, monkeypatch):
    from ontocore.review.service import ReviewService

    captured: dict = {}

    def fake_accept(self, candidate_id, *, mode="create", target_iri=None):
        captured["id"] = candidate_id
        captured["mode"] = mode
        captured["target_iri"] = target_iri
        return {"id": candidate_id, "status": "accepted"}

    monkeypatch.setattr(ReviewService, "accept_type", fake_accept)
    client = TestClient(create_app(data_dir=tmp_path))
    empty = client.post("/api/type-candidates/cand-1/accept")
    assert empty.status_code == 200
    assert captured["mode"] == "create"
    assert captured["target_iri"] is None
    body = client.post(
        "/api/type-candidates/cand-1/accept",
        json={
            "mode": "overwrite",
            "target_iri": "https://ontocore.local/ns/working#Product",
        },
    )
    assert body.status_code == 200
    assert captured["mode"] == "overwrite"
    assert captured["target_iri"] == "https://ontocore.local/ns/working#Product"
