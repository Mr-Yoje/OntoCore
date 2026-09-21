# 故障码与日志排查 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 全项目失败都能在终端和按日轮转日志里看到故障码、中文说明、`request_id` 和完整堆栈；HTTP/作业带 `kind`；界面 tips 只显示中文并用左边线区分业务/系统。

**Architecture:** loguru 在 `create_app` 配一次（stderr + `{data_dir}/logs/ontocore_YYYY-MM-DD.log`）。领域异常统一为 `AppError`（`code`/`kind`/`http_status`）。中间件发 `request_id`。处理器写日志并返回 `{detail, code, kind, request_id}`。作业另存中文 `error` 与 `error_kind`，不含 `OC-`。前端按 `kind` 选 tips 样式，不渲染 `code`。

**Tech Stack:** FastAPI、loguru、pytest、Vite React vitest。

**Spec:** `docs/superpowers/specs/2026-09-21-fault-logging-design.md`

## Global Constraints

- 产品语言只用：对象、属性、关系、定义、实例、父对象、编号、供应商、数据源。禁止：类、TBox、ABox、对象属性、数据属性、领域包。
- 界面不展示故障码、不展示堆栈。`detail` / 作业 `error` / tips 不含 `OC-`、不含 `Traceback`、不含源码路径。未捕获对用户固定为「服务出错，请查看日志」。抽取/模型失败对用户用 `public_llm_message`，禁止把 `str(exc)` 原样返回前端。
- 日志 `diagnose=False`，不写 API Key、不写完整请求体。
- 测试禁止打真实供应商；后端临时 `data_dir`，不写本机 `backend/data/`。
- 新行为先失败测试再实现。TDD。
- 用户未说「提交」时不要 git commit / push。计划里的 commit 步骤仅在用户明确要求时执行。
- 工作区可能已有未按本计划审查的半成品。执行时以本任务步骤为准：先红后绿。若现有实现让测试立刻绿且从未见过红，删掉相关实现再走 TDD。

---

## File structure

```
backend/pyproject.toml                          # loguru 依赖
backend/src/ontocore/errors.py                   # AppError 谱系
backend/src/ontocore/faults.py                   # 新建：配置日志、log_fault、fault_body、public_llm_message
backend/src/ontocore/api/app.py                  # 中间件、统一异常、校验 raise BusinessError
backend/src/ontocore/jobs/store.py               # error_kind 列
backend/src/ontocore/jobs/service.py             # 记栈、作业 error / error_kind
backend/src/ontocore/extract/engine.py           # 抽取失败记 OC-3101 栈
backend/src/ontocore/extract/llm.py              # LiteLLM 异常记栈后包装
backend/tests/test_faults.py                     # 新建
backend/tests/test_api.py                        # 现有 400/503 仍绿；detail 不变
frontend/src/api.ts                              # ApiError.kind / code
frontend/src/tips.tsx                            # reportError；tip-business / tip-system
frontend/src/index.css                           # 左边线灰 / 深灰近黑
frontend/src/pages/*.tsx                         # API 失败走 reportError；作业失败按 error_kind
frontend/src/api.test.ts
```

---

### Task 1: loguru 按日轮转与 log_fault

**Files:**
- Modify: `backend/pyproject.toml`（`loguru>=0.7.3`，若尚未加入）
- Create: `backend/src/ontocore/faults.py`
- Test: `backend/tests/test_faults.py`（本任务先只放日志测试）

**Interfaces:**
- Consumes: `data_dir: Path`
- Produces:
  - `configure_logging(data_dir: str | Path) -> None`
  - `log_fault(*, code: str, kind: str, detail: str, request_id: str | None = None, exc: BaseException | None = None) -> None`
  - `new_request_id() -> str`
  - 落盘 `{data_dir}/logs/ontocore_YYYY-MM-DD.log`，`rotation="00:00"`，`retention="14 days"`，UTF-8，`diagnose=False`
  - `KIND_BUSINESS = "business"`，`KIND_SYSTEM = "system"`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_faults.py`：

```python
from pathlib import Path
from ontocore.faults import configure_logging, log_fault


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend; uv run pytest tests/test_faults.py::test_log_fault_writes_code_and_traceback -q`

Expected: FAIL（无 `ontocore.faults` 或无落盘）

- [ ] **Step 3: Write minimal implementation**

`faults.py`：`logger.remove()` 后 `add(sys.stderr)` 与 `add(log_dir / "ontocore_{time:YYYY-MM-DD}.log", rotation="00:00", retention="14 days", encoding="utf-8", backtrace=True, diagnose=False)`。`log_fault` 用 `logger.opt(exception=exc).error(...)`，并 `logger.error("".join(traceback.format_exception(...)))` 以保证文件中有 `Traceback` 字样。

- [ ] **Step 4: Run test to verify it passes**

Run: 同上。Expected: PASS

- [ ] **Step 5: Commit（仅当用户要求）**

```
git commit -m "feat: loguru 按日轮转并记录故障码堆栈"
```

---

### Task 2: AppError 谱系与 HTTP 错误体

**Files:**
- Modify: `backend/src/ontocore/errors.py`
- Modify: `backend/src/ontocore/faults.py`（增加 `fault_body`、`public_llm_message`）
- Modify: `backend/src/ontocore/api/app.py`（`create_app` 调 `configure_logging`；`request_id` 中间件；`AppError`/`KeyError`/`Exception` 处理器）
- Test: `backend/tests/test_faults.py`、现有 `tests/test_api.py::test_graph_unavailable_is_503`

**Interfaces:**
- Consumes: Task 1 的 `configure_logging` / `log_fault`
- Produces:
  - `class AppError(Exception)`：`code`, `kind`, `http_status`, `message`
  - `BusinessError`：默认 `kind="business"`, `http_status=400`
  - `SystemError`：默认 `kind="system"`, `http_status=500`
  - 现有 `ProfileViolation`→`OC-2001` business；`OntologyWriteError`→`OC-2002`；`ConflictError`→`OC-2003` 409；`IngressError`→`OC-3001`；`GraphUnavailable`→`OC-4001` system 503；`StructuredOutputError`→`OC-3101`
  - `fault_body(*, detail, code, kind, request_id) -> dict`
  - HTTP 错误 JSON：`detail`（不含 `OC-`）、`code`、`kind`、`request_id`
  - 请求头 `X-Request-ID` 可传入，否则生成；响应头带回
  - 未捕获：500、`OC-9001`、`kind=system`、`detail="服务出错，请查看日志"`
  - **TestClient 测 500 必须 `raise_server_exceptions=False`**，否则会把异常再抛给 pytest

- [ ] **Step 1: Write the failing tests**

追加到 `test_faults.py`：

```python
from fastapi.testclient import TestClient
from ontocore.api.app import create_app
from ontocore.jobs.service import JobService


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
    assert "OC-" not in body["detail"]
    text = next((tmp_path / "logs").glob("ontocore_*.log")).read_text(encoding="utf-8")
    assert "Traceback" in text
    assert "disk exploded" in text
    assert "OC-9001" in text
```

`create_job` 缺供应商改为 `raise BusinessError("请选择供应商", code="OC-1101")`（本任务实现时一起做）。图 503 仍断言 `detail` 含「图不可用」，可额外含 `code`。

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_faults.py::test_validation_error_has_code_kind_and_request_id tests/test_faults.py::test_unhandled_exception_is_system_500_and_logged -q`

Expected: FAIL（无 `code` 或 TestClient 直接抛 `RuntimeError`）

- [ ] **Step 3: Write minimal implementation**

- `errors.py` 如上谱系。`ConflictError` 仍暴露 `.message`。`raise GraphUnavailable from exc` 无参时默认「图不可用」。
- `create_app` 开头 `configure_logging(root)`。
- 中间件设置 `request.state.request_id`。
- `@app.exception_handler(AppError)` 记日志并返回 `fault_body`。`OntologyWriteError` 仍走现有 `_write_detail`。`GraphUnavailable` 的 `detail` 固定「图不可用」。
- `KeyError` → 404 `OC-1004` business「未找到」。
- `Exception`：若是 `StarletteHTTPException` / `RequestValidationError` 交给 FastAPI 默认处理器；否则 500 `OC-9001`。
- `POST /api/jobs` 六条校验 `raise BusinessError(..., code="OC-1101"` … `OC-1106")`。
- 设置拉取/测联通失败 `raise BusinessError(..., code="OC-5001")`。测联通缺模型文案可仍为「请选择具体模型」（设置页用语）。

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_faults.py tests/test_api.py -q`

Expected: PASS。现有 `detail` 断言不因多了 `code` 失败。

- [ ] **Step 5: Commit（仅当用户要求）**

```
git commit -m "feat: HTTP 错误带故障码与 request_id"
```

---

### Task 3: 作业 error_kind 与抽取/判重记栈

**Files:**
- Modify: `backend/src/ontocore/jobs/store.py`
- Modify: `backend/src/ontocore/jobs/service.py`
- Modify: `backend/src/ontocore/extract/engine.py`
- Modify: `backend/src/ontocore/extract/llm.py`
- Test: `backend/tests/test_faults.py`、现有 `test_post_jobs_extractor_error_is_not_500`

**Interfaces:**
- Consumes: `log_fault`、`public_llm_message`、`AppError`
- Produces:
  - `Job.error_kind: str | None`；SQLite `error_kind TEXT`，缺列 `ALTER`
  - `JobStore.set_status(job_id, status, error=None, error_kind=None)`
  - 作业 JSON 含 `error_kind`；`error` 中文且不含 `OC-`
  - 抽取块失败：日志 `OC-3101` + 栈；`block_failures[].reason` 与作业 `error` 为 `public_llm_message`
  - 判重 `except`：日志 `OC-3103` + 栈；`partial`，`error="判重失败"`，`error_kind="business"`
  - 抽取器未预期 `Exception`：作业 `failed`，`error_kind="system"`，`error="抽取失败"`（不要 `str(exc)`）。相应修改 `test_post_jobs_extractor_error_is_not_500`：仍 200、`status=failed`，`error` 为「抽取失败」，日志含 `llm down` 与栈。

`public_llm_message`：与现 `_probe_detail` 相同映射（密钥/超时/连接/404/429）；若原文含 `Traceback` 或 `File "` 则返回「模型调用失败」；否则原文截断 400 字且不得保留堆栈行。

- [ ] **Step 1: Write the failing test**

```python
from ontocore.extract.llm import LiteLlmGateway


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
```

`engine.extract` 须 `except Exception`（测试补丁替换整个 `_call`，不会变成 `StructuredOutputError`）。

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_faults.py::test_extract_failure_logs_traceback_and_job_error_kind -q`

Expected: FAIL（`error` 空或无 `error_kind` 或日志无栈）

- [ ] **Step 3: Write minimal implementation**

- `jobs` 表 `error_kind`；`set_status` 写入。
- `LlmExtractor`：`complete_structured` 失败则 `log_fault(code="OC-3101", ...)` 并 `BlockFailure(reason=public_llm_message(str(exc)))`。
- `JobService.run`：全块失败无候选 → `failed` + 首条 `reason` + `error_kind=business`；有候选 → `partial` 同样带 `error`。判重失败如上。`except AppError` / `except Exception` 分别 business/system。
- `LiteLlmGateway` 捕获供应商异常时同样 `log_fault` 再 `raise StructuredOutputError(public_llm_message(...)) from exc`。

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_faults.py tests/test_api.py::test_post_jobs_extractor_error_is_not_500 tests/test_llm_gateway.py tests/test_review_and_jobs.py -q`

Expected: PASS

- [ ] **Step 5: Commit（仅当用户要求）**

```
git commit -m "feat: 作业失败写入 error_kind 并记录抽取堆栈"
```

---

### Task 4: 前端 tips 业务灰 / 系统深灰，不展示故障码

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/tips.tsx`
- Modify: `frontend/src/index.css`
- Modify: `frontend/src/pages/UploadPage.tsx`（及其它 `showTip("error", tipText(e))` 的页面）
- Test: `frontend/src/api.test.ts`

**Interfaces:**
- Consumes: HTTP `kind`、`detail`；作业 `error`、`error_kind`
- Produces:
  - `ApiError` 增加 `kind: "business" | "system"`、`code: string`（解析响应，页面不展示 `code`）
  - `reportError(showTip, error)`：`kind===system` → `showTip("system", detail)`，否则 `business`
  - `.tip-ok` 主色左边线；`.tip-business`（及兼容的 `.tip-error`）`#98a2b3`；`.tip-system` `#161b26`
  - `tips.tsx` 源码含字面量 `tip-business`、`tip-system`；**不含** `OC-`
  - 数据源页：作业 `error` 用 `error_kind` 选 tip；HTTP 失败用 `reportError`

- [ ] **Step 1: Write the failing test**

在 `shows flash messages as popup tips` 中增加：

```typescript
expect(tips.includes("tip-business")).toBe(true);
expect(tips.includes("tip-system")).toBe(true);
expect(css.includes("tip-business")).toBe(true);
expect(css.includes("tip-system")).toBe(true);
expect(api.includes("kind")).toBe(true);
expect(tips.includes("OC-")).toBe(false);
    expect(tips.includes("Traceback")).toBe(false);
```

`parse` 从 JSON 读 `kind`/`code`。`TipHost` 渲染 `className` 含 `tip-business` / `tip-system`。

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend; npx vitest run src/api.test.ts`

Expected: FAIL（无 `tip-business`）

- [ ] **Step 3: Write minimal implementation**

- `ApiError` 构造带 `kind`/`code`；`parse` 非 2xx 时读取。
- `reportError`；各页 `catch` 改 `reportError(showTip, e)`。本地校验（如「请先拉取模型列表」）可继续 `showTip("error", ...)`，并在 `TipHost` 把 `error` 映射为 `business` 样式。
- 作业：`created.error` 时 `showTip(created.error_kind === "system" ? "system" : "business", created.error)`。

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/api.test.ts`

Expected: PASS

- [ ] **Step 5: 浏览器核对**

打开 `http://localhost:5173`（或当前 Vite 端口）。数据源页不填供应商提交（或触发 400）：tips 中文、左边线灰、无 `OC-`。若后端未起，先起 8001 + 前端。系统异常路径可用作业失败 `error_kind=system` 的既有失败作业，或临时看 CSS。

- [ ] **Step 6: Commit（仅当用户要求）**

```
git commit -m "feat: tips 按业务与系统区分左边线"
```

---

## Self-review

| 规格条款 | 任务 |
| --- | --- |
| loguru、按日轮转、14 天、UTF-8、diagnose 关 | Task 1 |
| 终端 + 文件、码、request_id、栈 | Task 1–2 |
| HTTP `{detail,code,kind,request_id}`、校验码 OC-110x | Task 2 |
| 业务异常也记日志 | Task 2 `log_fault` |
| 作业 error 无 OC-、error_kind、抽取/判重栈 | Task 3 |
| 未捕获 500 OC-9001 | Task 2（TestClient `raise_server_exceptions=False`） |
| 界面无码；业务灰、系统深灰近黑 | Task 4 |
| 不做 Sentry / 界面堆栈 / 密钥入日志 | 各任务约束 |

无 TBD。`error_kind` 在 Task 3 定义，Task 4 读取，名称一致。
