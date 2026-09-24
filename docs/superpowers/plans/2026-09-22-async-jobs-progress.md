# 异步作业、全量列表与切片进度 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 数据源页以全量作业列表为主；新建抽取走弹窗；点行开作业卡；`POST /api/jobs` 异步立即返回；按切片更新进度；规格预留后续 Celery。

**Architecture:** JobStore 增加 `created_at`、`progress_done`、`progress_total`；`GET /api/jobs` 全量倒序。API 创建后线程池跑 `JobService.run`（传入已读 bytes）。抽取循环内每完成一切片 `set_progress`。前端列表 + 双弹窗 + 轮询。

**Tech Stack:** FastAPI、SQLite、线程池、React、vitest、pytest。

**Spec:** `docs/superpowers/specs/2026-09-22-async-jobs-progress-design.md`

## Global Constraints

- 产品文案：对象、属性、关系、定义、实例、父对象、编号、供应商、数据源。
- 界面状态只中文；不展示 `OC-`；作业 `error` 走故障码对照表。
- 进度 = floor(done/total*100)；判重不计入切片。
- 列表 = **全部**作业，时间倒序；不是最近 20 条。
- 本轮线程池；不做 Celery 落地。
- 禁止 wsl/bash；PowerShell。TDD。用户未说提交则不 commit。
- 测试禁止真实供应商；临时 data_dir。

---

## File map

| 文件 | 职责 |
| --- | --- |
| `backend/src/ontocore/jobs/store.py` | created_at、progress_*、list_jobs、set_progress |
| `backend/src/ontocore/error_catalog.py` | OC-3108 服务已重启，请重新抽取 |
| `backend/src/ontocore/extract/engine.py` | 切块循环回调进度 |
| `backend/src/ontocore/jobs/service.py` | 解析后设 total；传进度回调 |
| `backend/src/ontocore/jobs/runner.py` | 新建：线程池提交 run |
| `backend/src/ontocore/api/app.py` | 异步 POST；GET /api/jobs；启动 fail stuck |
| `frontend/src/api.ts` | listJobs；类型字段 |
| `frontend/src/pages/UploadPage.tsx` | 列表为主、新建弹窗、详情弹窗、轮询 |
| `frontend/src/jobStatus.ts` | 状态中文映射（可单测） |
| tests / api.test.ts | 覆盖 |

---

### Task 1: JobStore 时间与进度 + 全量列表

**Files:** `jobs/store.py`；`tests/test_review_and_jobs.py` 或新建 `tests/test_job_store.py`

**Produces:**
- `Job.created_at: str`（ISO UTC 或本地可排序字符串）
- `Job.progress_done: int = 0`、`Job.progress_total: int = 0`
- `list_jobs() -> list[Job]` 全量，`ORDER BY created_at DESC`
- `set_progress(job_id, done, total) -> Job`
- ALTER 加列；旧行 `created_at` 用当前时间或空串排后

- [ ] **Step 1:** 失败测试：create 两笔，`list_jobs` 新在前；`set_progress` 可读回
- [ ] **Step 2:** 实现列与方法
- [ ] **Step 3:** 绿；跳过 commit

---

### Task 2: 抽取进度回调 + OC-3108

**Files:** `error_catalog.py`、`errors.py`（若需）、`extract/engine.py`、`jobs/service.py`、`tests/test_faults.py`（catalog）、抽取相关测

**Produces:**
- Catalog `OC-3108` / detail「服务已重启，请重新抽取」
- `LlmExtractor.extract(..., on_chunk_done: Callable[[int, int], None] | None = None)`：`texts = extract_texts(doc)` 后先可调 `on_chunk_done(0, n)`；每完成一块（成功或 failure append 后）`on_chunk_done(i, n)`
- `JobService.run`：解析后 `set_progress(0, len(extract_texts(doc)))`；callback 写 store

- [ ] **Step 1:** 测 Fake LLM 多块文时 progress 递增到 total（可用 monkeypatch extract_texts 返回多段）
- [ ] **Step 2:** 实现
- [ ] **Step 3:** catalog 测试含 OC-3108；跳过 commit

---

### Task 3: 异步 API + 列表 + 启动清理

**Files:** `jobs/runner.py`、`api/app.py`、`tests/test_api.py`、`tests/test_faults.py`

**Produces:**
- `JobRunner.submit(job_id, filename, data)` 线程池；同进程
- `POST /api/jobs`：create → submit → **立即** `return _dump(jobs.get(id))`（status queued 或已 running）
- `GET /api/jobs` → `list_jobs()`
- `create_app` lifespan/startup：`fail_interrupted_jobs()` 将 queued/running → failed + OC-3108 文案
- 既有同步假设的测试改为：POST 后 poll GET 直到终态，或 `runner` 在测试里用同步执行钩子

测试模式：可用 `JobRunner(sync=True)` 或环境变量，避免 flaky；默认生产异步。

- [ ] **Step 1:** 测 POST 立即非 completed；sync 模式跑完后 GET completed；GET /api/jobs 含该 id
- [ ] **Step 2:** 实现
- [ ] **Step 3:** 全量相关 API 测绿

---

### Task 4: 前端列表 + 双弹窗 + 轮询

**Files:** `api.ts`、`jobStatus.ts`、`UploadPage.tsx`、`api.test.ts`、必要时 `index.css`

**Produces:**
- `listJobs()`、`Job` 类型含 progress_*、created_at
- `jobStatusLabel(status)` 中文表（规格 §5）
- UploadPage：主区列表；「新建抽取」弹窗表单；点行作业卡弹窗；queued/running 轮询 1–2s 刷新当前卡与列表；显示进度 `done/total` 或 `%`
- 扫描测试：列表、dialog、listJobs、去审阅

- [ ] **Step 1:** 失败的 api.test 接线断言
- [ ] **Step 2:** 实现 UI
- [ ] **Step 3:** vitest 绿；浏览器主路径（若服务在跑）

---

### Task 5: 回归

- [ ] backend `pytest -q`；frontend `vitest run`
- [ ] 对照规格自检：全量列表、异步、进度、Celery 仅文档

---

## Spec coverage

| 规格点 | Task |
| --- | --- |
| created_at + 全量倒序 | 1, 3 |
| progress_done/total + 切片回调 | 2 |
| 异步 POST + runner + 重启失败 | 3 |
| 列表/新建弹窗/作业卡/轮询/中文状态 | 4 |
| Celery 预留 | 文档已有，不实现 |
| OC-3108 | 2, 3 |
