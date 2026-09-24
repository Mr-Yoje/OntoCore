# 故障码对照表细化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地「一个码 ↔ 一句固定中文」对照表：HTTP `detail`、作业 `error`、tips 与表完全一致；界面仍不展示故障码。

**Architecture:** 新建 `error_catalog.py` 为唯一文案源。`AppError` 以 `code` 构造并从表取 `detail`/`kind`/`http_status`。供应商异常经 `map_provider_fault` 映射到 5xxx（设置）或 31xx（作业）后再取表文。前端 `sanitizePublicError` 仅作断网/堆栈兜底，细分文案以后端为准。

**Tech Stack:** FastAPI、pytest、Vite React vitest。

**Spec:** `docs/superpowers/specs/2026-09-21-fault-logging-design.md`（§3.1 完整对照表、§4 落到代码）。

## Global Constraints

- 产品语言只用：对象、属性、关系、定义、实例、父对象、编号、供应商、数据源。
- 界面不展示故障码、不展示堆栈。`detail` / 作业 `error` / tips 不含 `OC-`、不含 `Traceback`、不含源码路径。
- 一个码一句固定中文；禁止调用点手写与对照表冲突的 `detail`。
- 测试禁止打真实供应商；后端临时 `data_dir`。
- 新行为先失败测试再实现（TDD）。
- **禁止运行 `wsl` / `bash.exe` / `wsl.exe`**（本机无 WSL，会弹安装框）。Shell 只用 PowerShell。
- 用户未说「提交」时不要 git commit / push。计划中的 Commit 步骤跳过，除非用户明确要求。

---

## File map

| 文件 | 职责 |
| --- | --- |
| `backend/src/ontocore/error_catalog.py` | 新建：`FAULTS` 字典、`fault_entry(code)`、`fault_detail(code)` |
| `backend/src/ontocore/errors.py` | `AppError` 只传 code 时从表填 message/kind/http_status |
| `backend/src/ontocore/faults.py` | `map_provider_fault`；`public_llm_message` 改为经映射取表文（保留旧名兼容测试可改） |
| `backend/src/ontocore/api/app.py` | 设置/上传校验与探测用新码；handler 的 detail 一律 `fault_detail(exc.code)` |
| `backend/src/ontocore/extract/llm.py` | LiteLLM 失败 → map job 码 → StructuredOutputError(code=…) |
| `backend/src/ontocore/extract/engine.py` | BlockFailure / log 用表文 |
| `backend/src/ontocore/jobs/service.py` | 作业 error 用表文；判重 OC-3103 |
| `backend/src/ontocore/review/service.py` | 占用冲突 OC-2004–2006；对齐 OC-2007 |
| `backend/tests/test_faults.py` | 对照表完整、映射、设置/作业路径断言 |
| `backend/tests/test_api.py` / `test_review_and_jobs.py` | 随文案/码变更更新断言 |
| `frontend/src/api.ts` | sanitize 兜底句与表一致 |
| `frontend/src/api.test.ts` | 同步断言 |

---

### Task 1: 对照表模块 + 查表 API（TDD）

**Files:**
- Create: `backend/src/ontocore/error_catalog.py`
- Modify: `backend/tests/test_faults.py`
- Test: `backend/tests/test_faults.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `FAULTS: dict[str, dict]` 键为 `OC-xxxx`，值含 `kind: str`、`http_status: int`、`detail: str`
  - `def fault_entry(code: str) -> dict`（未知码抛 `KeyError`）
  - `def fault_detail(code: str) -> str`

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_faults.py` 追加：

```python
EXPECTED_FAULTS = {
    "OC-1101": ("business", 400, "请选择供应商"),
    "OC-1102": ("business", 400, "请选择抽取模型"),
    "OC-1103": ("business", 400, "请选择嵌入模型"),
    "OC-1104": ("business", 400, "请选择嵌入供应商"),
    "OC-1105": ("business", 400, "未找到所选供应商，请先在设置中添加"),
    "OC-1106": ("business", 400, "未找到所选嵌入供应商，请先在设置中添加"),
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
```

- [ ] **Step 2: 跑测试确认失败**

```powershell
cd D:\Document\PAProject\OntoCore\backend
$env:PYTHONIOENCODING = "utf-8"
.\.venv\Scripts\python.exe -m pytest tests/test_faults.py::test_error_catalog_matches_spec -q
```

Expected: FAIL（`ModuleNotFoundError` 或 `ImportError`）

- [ ] **Step 3: 实现 `error_catalog.py`**

```python
from __future__ import annotations

FAULTS: dict[str, dict] = {
    "OC-1101": {"kind": "business", "http_status": 400, "detail": "请选择供应商"},
    "OC-1102": {"kind": "business", "http_status": 400, "detail": "请选择抽取模型"},
    "OC-1103": {"kind": "business", "http_status": 400, "detail": "请选择嵌入模型"},
    "OC-1104": {"kind": "business", "http_status": 400, "detail": "请选择嵌入供应商"},
    "OC-1105": {
        "kind": "business",
        "http_status": 400,
        "detail": "未找到所选供应商，请先在设置中添加",
    },
    "OC-1106": {
        "kind": "business",
        "http_status": 400,
        "detail": "未找到所选嵌入供应商，请先在设置中添加",
    },
    "OC-1004": {"kind": "business", "http_status": 404, "detail": "未找到"},
    "OC-2001": {"kind": "business", "http_status": 400, "detail": "不符合对象关系约束"},
    "OC-2002": {"kind": "business", "http_status": 400, "detail": "无法写入对象、属性或关系"},
    "OC-2003": {"kind": "business", "http_status": 409, "detail": "与已有数据冲突"},
    "OC-2004": {"kind": "business", "http_status": 409, "detail": "仍有实例占用该对象"},
    "OC-2005": {"kind": "business", "http_status": 409, "detail": "仍有实例占用该属性"},
    "OC-2006": {"kind": "business", "http_status": 409, "detail": "仍有实例占用该关系"},
    "OC-2007": {
        "kind": "business",
        "http_status": 400,
        "detail": "请选择要对齐的已有对象或关系",
    },
    "OC-3001": {"kind": "business", "http_status": 400, "detail": "无法提取文本"},
    "OC-3101": {"kind": "business", "http_status": 400, "detail": "模型调用失败"},
    "OC-3102": {
        "kind": "business",
        "http_status": 400,
        "detail": "密钥无效或未填写，请检查 API Key",
    },
    "OC-3103": {"kind": "business", "http_status": 400, "detail": "判重失败"},
    "OC-3104": {
        "kind": "business",
        "http_status": 400,
        "detail": "连接超时，请检查 Base URL 或网络",
    },
    "OC-3105": {"kind": "business", "http_status": 400, "detail": "无法连接服务，请检查网络"},
    "OC-3106": {
        "kind": "business",
        "http_status": 400,
        "detail": "接口不存在，请检查 Base URL 和模型名称",
    },
    "OC-3107": {"kind": "business", "http_status": 400, "detail": "请求过于频繁，请稍后再试"},
    "OC-4001": {"kind": "system", "http_status": 503, "detail": "图不可用"},
    "OC-5001": {"kind": "business", "http_status": 400, "detail": "请填写 Base URL"},
    "OC-5002": {"kind": "business", "http_status": 400, "detail": "请填写 API Key"},
    "OC-5003": {"kind": "business", "http_status": 400, "detail": "请选择具体模型"},
    "OC-5004": {
        "kind": "business",
        "http_status": 400,
        "detail": "密钥无效或未填写，请检查 API Key",
    },
    "OC-5005": {
        "kind": "business",
        "http_status": 400,
        "detail": "连接超时，请检查 Base URL 或网络",
    },
    "OC-5006": {"kind": "business", "http_status": 400, "detail": "无法连接服务，请检查网络"},
    "OC-5007": {
        "kind": "business",
        "http_status": 400,
        "detail": "接口不存在，请检查 Base URL 和模型名称",
    },
    "OC-5008": {"kind": "business", "http_status": 400, "detail": "请求过于频繁，请稍后再试"},
    "OC-5009": {"kind": "business", "http_status": 400, "detail": "模型调用失败"},
    "OC-9001": {"kind": "system", "http_status": 500, "detail": "服务出错，请查看日志"},
}


def fault_entry(code: str) -> dict:
    return FAULTS[code]


def fault_detail(code: str) -> str:
    return FAULTS[code]["detail"]
```

- [ ] **Step 4: 跑测试确认通过**

同 Step 2 命令。Expected: PASS

- [ ] **Step 5: Commit**（用户未要求则跳过）

---

### Task 2: `map_provider_fault` + `AppError` 从表构造（TDD）

**Files:**
- Modify: `backend/src/ontocore/faults.py`
- Modify: `backend/src/ontocore/errors.py`
- Modify: `backend/tests/test_faults.py`

**Interfaces:**
- Consumes: `fault_detail`, `FAULTS` from Task 1
- Produces:
  - `def map_provider_fault(raw: str, *, domain: Literal["settings", "job"]) -> str` → `OC-5xxx` 或 `OC-31xx`
  - `def public_llm_message(raw: str, *, domain: str = "settings") -> str` → `fault_detail(map_provider_fault(...))`（兼容旧调用）
  - `AppError.__init__(self, message: str = "", *, code: str | None = None, ...)`：若给了 `code`，用表覆盖 `message`/`kind`/`http_status`；仅 `BusinessError("请选择供应商", code="OC-1101")` 也以表为准

映射规则（与现 `public_llm_message` 一致，输出改为码）：

| raw 特征 | settings | job |
| --- | --- | --- |
| credential / api_key / unauthorized / 401 | OC-5004 | OC-3102 |
| timeout / timed out | OC-5005 | OC-3104 |
| offline（现 `_looks_like_offline`） | OC-5006 | OC-3105 |
| 404 / not found | OC-5007 | OC-3106 |
| 429 | OC-5008 | OC-3107 |
| dump / 非中文 / 其余 | OC-5009 | OC-3101 |

注意：原「保留纯中文如模型列表为空」改为归入 OC-5009 / OC-3101（规格无该独立句）。

- [ ] **Step 1: 写失败测试**

```python
def test_map_provider_fault_settings_and_job():
    from ontocore.faults import map_provider_fault, public_llm_message
    from ontocore.error_catalog import fault_detail

    assert map_provider_fault("401 Unauthorized", domain="settings") == "OC-5004"
    assert map_provider_fault("401 Unauthorized", domain="job") == "OC-3102"
    assert map_provider_fault("[Errno 11001] getaddrinfo failed", domain="settings") == "OC-5006"
    assert map_provider_fault("timed out", domain="job") == "OC-3104"
    assert map_provider_fault("litellm.InternalServerError", domain="settings") == "OC-5009"
    assert public_llm_message("401 Unauthorized", domain="job") == fault_detail("OC-3102")


def test_business_error_detail_comes_from_catalog():
    from ontocore.errors import BusinessError
    from ontocore.error_catalog import fault_detail

    exc = BusinessError("会被覆盖的手写文案", code="OC-5001")
    assert exc.code == "OC-5001"
    assert exc.message == fault_detail("OC-5001")
    assert str(exc) == fault_detail("OC-5001")
    assert exc.kind == "business"
    assert exc.http_status == 400
```

- [ ] **Step 2: 跑测试确认失败**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_faults.py::test_map_provider_fault_settings_and_job tests/test_faults.py::test_business_error_detail_comes_from_catalog -q
```

Expected: FAIL

- [ ] **Step 3: 实现映射与 AppError**

在 `faults.py`：把现有 `public_llm_message` 逻辑拆成先出码再 `fault_detail`。保留 `_looks_like_offline` / `_looks_like_dump`。

在 `errors.py`：

```python
from ontocore.error_catalog import FAULTS

class AppError(Exception):
    code = "OC-9001"
    kind = "system"
    http_status = 500

    def __init__(
        self,
        message: str = "",
        *,
        code: str | None = None,
        kind: str | None = None,
        http_status: int | None = None,
    ) -> None:
        if code is not None:
            self.code = code
        entry = FAULTS.get(self.code)
        if entry is not None:
            self.message = entry["detail"]
            self.kind = entry["kind"]
            self.http_status = entry["http_status"]
        else:
            self.message = message
            if kind is not None:
                self.kind = kind
            if http_status is not None:
                self.http_status = http_status
        super().__init__(self.message)
```

子类默认 `code` 仍指向表内码（`GraphUnavailable` → OC-4001 等）。`ConflictError` 等可改为只 `super().__init__(code="OC-2003")`。

- [ ] **Step 4: 更新旧 `public_llm_message_*` 测试**

凡断言「模型列表为空」保留原文的，改为断言「模型调用失败」。其它映射断言改为与 `fault_detail` 一致。

跑：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_faults.py -q
```

Expected: 全绿

- [ ] **Step 5: Commit**（用户未要求则跳过）

---

### Task 3: API 设置 / 上传 / 异常处理器接表

**Files:**
- Modify: `backend/src/ontocore/api/app.py`
- Modify: `backend/tests/test_faults.py`（必要时 `test_api.py`）

**Interfaces:**
- Consumes: `BusinessError(code=...)`、`map_provider_fault`、`fault_detail`
- Produces: 设置探测与校验返回拆细码；handler `detail` 恒为表文

- [ ] **Step 1: 写失败测试**

```python
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
```

（若已有 `test_settings_models_maps_offline_dns` 只断言 detail，改为同时断言 `code == "OC-5006"`。）

- [ ] **Step 2: 跑测试确认失败**（仍返回万能 OC-5001 时失败）

- [ ] **Step 3: 改 `app.py`**

- 拉取模型 / 测试：缺 Base URL → `BusinessError(code="OC-5001")`；缺 API Key → `OC-5002`；缺模型 → `OC-5003`。
- `except` 探测失败：`code = map_provider_fault(str(exc), domain="settings")`；`raise BusinessError(code=code) from exc`。
- 删除 `_probe_detail` / 对 `OntologyWriteError` 的 `_write_detail` 自由改写；`app_error_handler` 使用 `detail = fault_detail(exc.code)`（或 `exc.message`，二者应已相同）。
- `KeyError` → 仍 OC-1004；未捕获 → OC-9001。

- [ ] **Step 4: 跑相关测试**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_faults.py tests/test_api.py -q
```

Expected: PASS。修复任何仍期望旧万能码或旧 `_write_detail` 自由文案的断言。

- [ ] **Step 5: Commit**（跳过除非用户要求）

---

### Task 4: 作业 / 抽取 / 审阅接表

**Files:**
- Modify: `backend/src/ontocore/extract/llm.py`
- Modify: `backend/src/ontocore/extract/engine.py`
- Modify: `backend/src/ontocore/jobs/service.py`
- Modify: `backend/src/ontocore/review/service.py`
- Modify: `backend/tests/test_faults.py`、`backend/tests/test_review_and_jobs.py`

**Interfaces:**
- Consumes: `map_provider_fault(..., domain="job")`、`fault_detail`、`BusinessError`/`StructuredOutputError`/`ConflictError` 带 code
- Produces: 作业 `error` 为表固定句；日志码为 31xx / 200x

- [ ] **Step 1: 写/改失败测试**

```python
def test_llm_gateway_maps_401_to_oc_3102(monkeypatch):
    from ontocore.errors import StructuredOutputError
    from ontocore.extract.llm import LiteLlmGateway

    def boom(*args, **kwargs):
        raise RuntimeError("401 Unauthorized")

    monkeypatch.setattr("litellm.completion", boom)  # 按现有 mock 点调整
    gw = LiteLlmGateway(api_base="https://x", api_key="sk", model="m")
    try:
        gw.complete_json("hi")  # 使用实际方法名
        assert False, "expected error"
    except StructuredOutputError as exc:
        assert exc.code == "OC-3102"
        assert str(exc) == "密钥无效或未填写，请检查 API Key"
```

（对照 `llm.py` 真实方法名与现有测试写法；有则改断言，无则新增。）

审阅占用：

```python
# 在现有占用冲突测试上断言 code/detail
assert ... code == "OC-2004" 且 detail == "仍有实例占用该对象"
```

判重失败作业 `error == "判重失败"`，日志含 `OC-3103`（已有则核对 detail 仍为表文）。

- [ ] **Step 2: 跑测试确认失败**

- [ ] **Step 3: 实现**

- `llm.py`：`code = map_provider_fault(str(exc), domain="job")`；`log_fault(code=code, detail=fault_detail(code), ...)`；`raise StructuredOutputError(code=code) from exc`（`StructuredOutputError` 默认码改为构造时传入）。
- `engine.py`：块失败 reason / log 用 `fault_detail(map...)` 或异常上的 message。
- `jobs/service.py`：`IngressError` → 表文「无法提取文本」；判重 → OC-3103；未捕获用户可见改为 `fault_detail("OC-9001")`（不要把 `str(exc)` 写入作业 error）。
- `review/service.py`：
  - 占用对象 → `ConflictError` 或 `BusinessError(code="OC-2004")`
  - 属性 → OC-2005；关系 → OC-2006
  - 未选对齐目标 → OC-2007
  - 通用冲突 → OC-2003

- [ ] **Step 4: 跑测试**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_faults.py tests/test_review_and_jobs.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**（跳过除非用户要求）

---

### Task 5: 前端兜底与接线测试

**Files:**
- Modify: `frontend/src/api.ts`（若文案已一致可不动逻辑，只核对）
- Modify: `frontend/src/api.test.ts`

**Interfaces:**
- Consumes: 后端返回的固定 `detail`
- Produces: 断网 / dump 兜底句与表一致；不渲染 `OC-`

- [ ] **Step 1: 更新/补充测试**

```typescript
it("offline and dump fallbacks match fault catalog copy", async () => {
  const { sanitizePublicError } = await import("./api");
  expect(sanitizePublicError("[Errno 11001] getaddrinfo failed")).toBe(
    "无法连接服务，请检查网络",
  );
  expect(sanitizePublicError("litellm.InternalServerError HTML")).toBe("模型调用失败");
  expect(sanitizePublicError("请填写 Base URL")).toBe("请填写 Base URL");
});
```

确认现有「ApiError 带 dump detail → 模型调用失败」仍绿。本地 `providerSaveTip` 不要求 OC 码。

- [ ] **Step 2: 跑**

```powershell
cd D:\Document\PAProject\OntoCore\frontend
npx vitest run src/api.test.ts
```

Expected: PASS

- [ ] **Step 3: 若后端已起，手工抽查**（可选）

打开设置 → 空 Base URL 拉取模型 → tips「请填写 Base URL」；断网或坏 URL →「无法连接服务，请检查网络」。tips 无 `OC-`。

- [ ] **Step 4: Commit**（跳过除非用户要求）

---

### Task 6: 全量回归

- [ ] **Step 1: 后端**

```powershell
cd D:\Document\PAProject\OntoCore\backend
$env:PYTHONIOENCODING = "utf-8"
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: 全绿

- [ ] **Step 2: 前端**

```powershell
cd D:\Document\PAProject\OntoCore\frontend
npx vitest run
```

Expected: 全绿

- [ ] **Step 3: 自检规格**

对照 `docs/superpowers/specs/2026-09-21-fault-logging-design.md` §3.1：每个码在 `error_catalog.FAULTS` 中存在且文案一致；无万能 OC-5001 覆盖探测失败。

---

## Spec coverage (self-review)

| 规格点 | 任务 |
| --- | --- |
| §3.1 完整对照表 | Task 1 |
| 一码固定文案 / AppError 从表 | Task 2 |
| map_provider_fault settings/job | Task 2–4 |
| 设置拆码 5001–5009 | Task 3 |
| 作业 31xx、判重 3103 | Task 4 |
| 占用 2004–2006、对齐 2007 | Task 4 |
| 界面不显示码、sanitize 兜底 | Task 5 |
| 测试与回归 | Task 1–6 |

无 TBD。Commit 步骤默认跳过（个人仓库约定）。
