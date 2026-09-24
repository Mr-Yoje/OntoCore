# 作业内去重、阶段状态与分阶段进度 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 多切片抽取后先作业内合并对象/关系，再对库判重；作业状态拆成抽取中/合并中/判重中/待审阅，且三阶段各自计算进度百分比。

**Architecture:** 在 `JobService.run` 中按 `extracting` → `merging` → `aligning` → 终态编排。新建 `extract/merge.py` 负责规范化、成簇、每簇一次模型合并与编号改挂。`attach_similar` 保留，前后由 service 写 `aligning` 进度（分母 2）。状态码写入新值；读路径兼容旧 `running`/`completed`/`partial`。

**Tech Stack:** FastAPI、SQLite、现有 `LlmGateway` / Fake LLM、pytest、React、vitest。

**Spec:** `docs/superpowers/specs/2026-09-23-job-dedup-status-design.md`（交互见 `2026-09-22-async-jobs-progress-design.md`）

## Global Constraints

- 产品文案：对象、属性、关系、定义、实例、父对象、编号、供应商、数据源。
- 界面状态只中文；tips 不展示 `OC-`；作业 `error` 走故障码对照表。
- 合并阈值固定 **0.85**；设置不暴露。
- 对库判重仍挂 `similar_to`，人审三种导入不变；不打真实供应商。
- 禁止 wsl/bash；PowerShell。TDD：先失败测试再实现。
- **用户未明确说「提交」则跳过所有 commit 步骤。**

---

## File map

| 文件 | 职责 |
| --- | --- |
| `backend/src/ontocore/models.py` | 扩展 `JobStatus` Literal |
| `backend/src/ontocore/jobs/store.py` | `fail_interrupted` 覆盖新进行中状态 |
| `backend/src/ontocore/jobs/service.py` | 全链路阶段状态 + 进度 + 调用 merge |
| `backend/src/ontocore/extract/merge.py` | **新建**：规范化、成簇、模型合并、改挂 |
| `backend/src/ontocore/extract/dedup.py` | 基本不动；由 service 包一层进度 |
| `backend/src/ontocore/api/app.py` | start 允许集合；进行中拒绝 |
| `frontend/src/jobStatus.ts` | 新状态文案 + 旧码兼容 |
| `frontend/src/pages/UploadPage.tsx` | REVIEWABLE / 进行中集合用新码+兼容 |
| `backend/tests/test_merge.py` | **新建** 成簇/合并单测 |
| `backend/tests/test_api.py` / `test_review_and_jobs.py` / `test_job_store.py` | 状态与流水线 |
| `frontend/src/api.test.ts` | 文案映射 |

---

### Task 1: JobStatus 类型与中断清理

**Files:**
- Modify: `backend/src/ontocore/models.py`
- Modify: `backend/src/ontocore/jobs/store.py`（`fail_interrupted_jobs`）
- Modify: `backend/tests/test_api.py`（`test_startup_fails_interrupted_jobs`）
- Modify: `backend/tests/test_job_store.py`（若有相关断言）

**Produces:**
- `JobStatus` 含：`queued` | `extracting` | `merging` | `aligning` | `reviewable` | `reviewable_partial` | `failed` | `types_accepted_graph_pending`，并**暂时保留**旧码 `running` | `completed` | `partial` 以便读库（写入新路径不再写旧码）。
- `fail_interrupted_jobs`：`WHERE status IN ('running','extracting','merging','aligning')`

**Consumes:** 无

- [ ] **Step 1: 写失败测试**

在 `test_api.py` 的 `test_startup_fails_interrupted_jobs` 中增加：创建后 `set_status` 为 `extracting` / `merging` / `aligning` 的作业，启动 app 后均为 `failed` 且 error 为 `OC-3108` 文案；`queued` 仍保留。

- [ ] **Step 2: 跑测确认失败（旧实现只清 running）**

```powershell
cd D:\Document\PAProject\OntoCore\backend
.\.venv\Scripts\python.exe -m pytest tests/test_api.py::test_startup_fails_interrupted_jobs -q --tb=short
```

Expected: FAIL 或断言不全。

- [ ] **Step 3: 扩展 Literal 与 fail SQL**

```python
JobStatus = Literal[
    "queued",
    "extracting",
    "merging",
    "aligning",
    "reviewable",
    "reviewable_partial",
    "failed",
    "types_accepted_graph_pending",
    # legacy read-compatible
    "running",
    "completed",
    "partial",
]
```

```sql
UPDATE jobs SET status = ?, error = ?, error_kind = ?
WHERE status IN ('running', 'extracting', 'merging', 'aligning')
```

- [ ] **Step 4: 跑测通过**

Expected: PASS

- [ ] **Step 5: Commit（仅当用户要求）**

---

### Task 2: API start 允许集 + 终态写入准备

**Files:**
- Modify: `backend/src/ontocore/api/app.py`（`start_job`）
- Modify: `backend/tests/test_api.py`（`test_start_job_rejects_running_status`、`test_restart_completed_job_resets_progress`）

**Produces:**
- 可 start：`queued` | `failed` | `reviewable` | `reviewable_partial` | `types_accepted_graph_pending` | 旧码 `completed` | `partial`
- 不可 start：`extracting` | `merging` | `aligning` | `running` → `OC-1107`
- 非 `queued` 可重抽：先 `set_status(queued, error=None)` + `set_progress(0,0)` 再 submit

**Interfaces:**
- 与 Task 6 对齐：service 将开始写 `extracting` 而非 `running`；本任务测「进行中拒绝」用 `set_status(..., "extracting")` 模拟。

- [ ] **Step 1: 调整拒绝测**

`test_start_job_rejects_running_status`：第一次 start 后若 sync fake 停在 `extracting`，第二次 start → 400 `OC-1107`。或直接 store `set_status(id, "merging")` 再 start。

- [ ] **Step 2: 扩展 start 白名单（含旧 completed/partial）**

与现逻辑一致，把 `completed`/`partial` 保留，加入 `reviewable`/`reviewable_partial`；拒绝集合改为进行中四态（含 `running`）。

- [ ] **Step 3: 跑相关 API 测**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_api.py -k "start_job or restart_completed or startup_fails" -q --tb=short
```

Expected: PASS

- [ ] **Step 4: Commit（仅当用户要求）**

---

### Task 3: 前端状态文案与可操作集合

**Files:**
- Modify: `frontend/src/jobStatus.ts`
- Modify: `frontend/src/pages/UploadPage.tsx`（`RUNNING`/`STARTABLE`/`REVIEWABLE`/`EDITABLE`）
- Modify: `frontend/src/api.test.ts`

**Produces:**

```ts
const LABELS: Record<string, string> = {
  queued: "待启动",
  extracting: "抽取中",
  merging: "合并中",
  aligning: "判重中",
  reviewable: "待审阅",
  reviewable_partial: "待审阅",
  failed: "失败",
  types_accepted_graph_pending: "待投影",
  // legacy
  running: "抽取中",
  completed: "待审阅",
  partial: "待审阅",
};
```

```ts
const RUNNING = new Set(["extracting", "merging", "aligning", "running"]);
const STARTABLE = new Set([
  "queued", "failed", "reviewable", "reviewable_partial",
  "completed", "partial", "types_accepted_graph_pending",
]);
const REVIEWABLE = new Set(["reviewable", "reviewable_partial", "completed", "partial"]);
const EDITABLE = new Set(["queued"]);
```

进度文案：`total<=0` 时若 status 在 RUNNING →「准备中」；`queued` →「—」。

- [ ] **Step 1: 改 api.test 期望**（`jobStatusLabel("extracting")` 等；`completed`/`partial` 仍为「待审阅」）
- [ ] **Step 2: 实现映射与集合**
- [ ] **Step 3:** `npm test -- --run src/api.test.ts` → PASS
- [ ] **Step 4: Commit（仅当用户要求）**

---

### Task 4: merge 模块 — 规范化与成簇（无 LLM）

**Files:**
- Create: `backend/src/ontocore/extract/merge.py`
- Create: `backend/tests/test_merge.py`

**Produces:**

```python
EMBED_MERGE_THRESHOLD = 0.85

def normalize_label(label: str) -> str:
    """strip; collapse whitespace; ASCII casefold."""

def cluster_objects(
    drafts: list[ObjectCandidateDraft],
    vectors: dict[str, list[float]] | None,
) -> list[list[ObjectCandidateDraft]]:
    """Same normalize_label -> one cluster; else cosine >= 0.85 merges (union-find)."""

def cluster_relations(
    drafts: list[RelationCandidateDraft],
    object_iri_map: dict[str, str],
    vectors: dict[str, list[float]] | None,
) -> list[list[RelationCandidateDraft]]:
    """Remap endpoints via object_iri_map; cluster by (norm label, src, tgt) or embed."""
```

成簇算法（对象）：
1. 按 `normalize_label(label)` 分桶，同桶先成簇。  
2. 各簇选代表（置信度最高，并列按 `iri` 字典序）。  
3. 若有 `vectors`：对代表两两算余弦，≥0.85 则 union-find 合并簇。  
4. 无向量：仅步骤 1。

- [ ] **Step 1: 失败测试**

```python
def test_normalize_label_collapses_space_and_case():
    assert normalize_label("  Foo   BAR ") == "foo bar"

def test_cluster_objects_by_same_normalized_name():
    a = ObjectCandidateDraft(iri="n1", label="重疾险", definition="d1", parent_iri=None, evidence="e1", block_id="b0", confidence=0.9)
    b = ObjectCandidateDraft(iri="n2", label="重疾险", definition="d2", parent_iri=None, evidence="e2", block_id="b1", confidence=0.8)
    clusters = cluster_objects([a, b], None)
    assert len(clusters) == 1 and {x.iri for x in clusters[0]} == {"n1", "n2"}

def test_cluster_objects_by_embed_threshold():
    # two different labels; fake vectors identical -> merge
    ...
```

- [ ] **Step 2:** `pytest tests/test_merge.py -q` → FAIL
- [ ] **Step 3: 实现 `normalize_label` / `cluster_*`（尚无 LLM）**
- [ ] **Step 4:** PASS
- [ ] **Step 5: Commit（仅当用户要求）**

---

### Task 5: merge 模块 — 每簇模型合并与改挂

**Files:**
- Modify: `backend/src/ontocore/extract/merge.py`
- Modify: `backend/tests/test_merge.py`

**Produces:**

```python
OBJECT_MERGE_SCHEMA: dict  # label, definition, parent_iri, evidence, attributes[{label,definition,literal_kind}]
RELATION_MERGE_SCHEMA: dict  # label, definition, source_iri, target_iri, evidence

def merge_extraction_result(
    result: ExtractionResult,
    llm: LlmGateway,
    *,
    embed: Callable[[list[str]], list[list[float]]] | None,
    on_cluster_done: Callable[[int, int], None] | None = None,
) -> tuple[ExtractionResult, bool]:
    """
    Returns (merged_result, had_merge_failures).
    - Build vectors if embed provided (label+definition texts).
    - Cluster objects; for len>=2 call llm once; pick representative iri (max confidence).
    - Build object_iri_map old->rep; rewrite attribute owner_iri, instance type_iri, instance_rel endpoints.
    - Cluster relations with map; merge len>=2.
    - on_cluster_done(done, total) where total = number of clusters with len>=2.
    - Merge failure: keep highest-confidence member of cluster; had_merge_failures=True.
    """
```

系统提示大意：「合并多条同义对象/关系为一条，保留各条定义与证据要点；对象输出含属性列表。」

- [ ] **Step 1: 测假 LLM 计数**

两对象同名 → `complete_structured` 调用 **1** 次；结果一条；属性 `owner_iri` 改到代表。

不同名、假 embed 向量相同 → 合并 1 次。

- [ ] **Step 2: FAIL then 实现**
- [ ] **Step 3: PASS**
- [ ] **Step 4: Commit（仅当用户要求）**

---

### Task 6: JobService 编排三阶段状态与进度

**Files:**
- Modify: `backend/src/ontocore/jobs/service.py`
- Modify: `backend/tests/test_review_and_jobs.py` 与/或 `tests/test_api.py`（终态断言 `completed`→`reviewable`）
- Modify: 所有写死 `"completed"` / `"partial"` / `"running"` 的后端测

**Produces:** `JobService.run` 伪码：

```python
def run(...):
    self._jobs.set_status(job_id, "extracting")
    self._jobs.set_progress(job_id, 0, 0)
    # parse ...
    n = len(extract_texts(doc))
    self._jobs.set_progress(job_id, 0, n)
    result = extractor.extract(..., on_chunk_done=lambda d, t: self._jobs.set_progress(job_id, d, t))
    extract_partial = bool(result.block_failures)

    self._jobs.set_status(job_id, "merging")
    self._jobs.set_progress(job_id, 0, 0)
    llm = self._make_llm(job)
    judge = self._judge_llm(job, llm)
    def on_cluster_done(d, t):
        self._jobs.set_progress(job_id, d, t)
    result, merge_failed = merge_extraction_result(
        result, llm,
        embed=(judge.embed if hasattr(judge, "embed") else None),
        on_cluster_done=on_cluster_done,
    )
    # 若 total 合并簇为 0：不强制停留，进度可保持 0,0

    self._jobs.set_status(job_id, "aligning")
    self._jobs.set_progress(job_id, 0, 2)
    try:
        # 嵌入在 attach_similar 内部；需拆开或回调：
        # 方案：给 attach_similar 增加 on_embed_done / 或 service 复制嵌入段后调精选。
        # 推荐最小改动：attach_similar(..., on_embed_finished: Callable[[], None] | None)
        #   嵌入尝试结束后调用 → service set_progress(1, 2)
        attach_similar(..., on_embed_finished=lambda: self._jobs.set_progress(job_id, 1, 2))
        self._jobs.set_progress(job_id, 2, 2)
    except StructuredOutputError / 判重失败:
        self._candidates.replace_job_results(...)
        return self._jobs.set_status(job_id, "reviewable_partial", error=..., error_kind=...)

    self._candidates.replace_job_results(job_id, result)
    if extract_partial or merge_failed or result.block_failures:
        return self._jobs.set_status(job_id, "reviewable_partial", error=first_reason, ...)
    if not _has_candidates(result) and failures:
        return failed
    return self._jobs.set_status(job_id, "reviewable")
```

**Interfaces:**
- Consumes: `merge_extraction_result`（Task 5）、`attach_similar`（扩展可选回调）
- Produces: 终态只写 `reviewable` / `reviewable_partial` / `failed`（不再写 `completed`/`partial`/`running`）

- [ ] **Step 1: 扩展 `attach_similar` 可选 `on_embed_finished: Callable[[], None] | None = None`**，在 embed try/except 结束后调用（无论成功失败跳过）。
- [ ] **Step 2: 集成测** — sync JobRunner：假多切片同名对象 → 最终 `reviewable`，type candidates 对象条数减少；状态曾可被轮询到（可用 list 记录 set_status 调用）。
- [ ] **Step 3: 批量替换测试中的终态字符串**
- [ ] **Step 4:** `pytest tests/ -q --tb=line` 相关失败修到绿
- [ ] **Step 5: Commit（仅当用户要求）**

---

### Task 7: 端到端进度与状态 API 验收

**Files:**
- Modify: `backend/tests/test_api.py`
- 可选：`backend/tests/test_dedup.py`

**Produces:** 显式测试：

1. `extracting` 进度：`progress_total == n_slices`，块完成后 `done` 递增。  
2. `merging`：假 2 条同名 → `progress_total == 1`，合并后 `done == 1`。  
3. `aligning`：embed 后 `done==1,total==2`；精选后 `done==2`。  
4. 无合并簇：不要求 `merging` 进度非零，终态仍 `reviewable`。  
5. 旧行 `completed` 仍可 start 重新抽取。

- [ ] **Step 1: 写上述测试（可用 monkeypatch 记录 status/progress 序列）**
- [ ] **Step 2: FAIL/PASS 循环**
- [ ] **Step 3:** 全量 `pytest -q` → PASS
- [ ] **Step 4: Commit（仅当用户要求）**

---

### Task 8: 规格落地标记与前端抽检

**Files:**
- Modify: `docs/superpowers/specs/2026-09-23-job-dedup-status-design.md` 文首状态改为「已落地」或「已确认（已实现）」
- 浏览器：数据源列表对待审阅显示「待审阅」+「审阅」；跑一小作业可见阶段文案（可用慢假 LLM 或日志）

- [ ] **Step 1: 更新规格状态行**
- [ ] **Step 2: `npm test -- --run` PASS**
- [ ] **Step 3: 打开 http://127.0.0.1:5173/upload 核对文案**
- [ ] **Step 4: Commit（仅当用户要求）**

---

## Spec coverage checklist

| 规格条款 | 任务 |
| --- | --- |
| 流水线 extracting→merging→aligning→终态 | Task 6 |
| 状态表与中断清理 | Task 1–2 |
| 兼容旧码读写/展示 | Task 1–3、7 |
| 抽取进度按切片 | Task 6–7 |
| 合并进度按簇；无簇跳过 | Task 5–7 |
| 判重进度 50%/100% | Task 6–7 |
| 规范化名 + 嵌入 0.85 成簇 | Task 4 |
| 每簇一次 LLM 合并 + 改挂 | Task 5 |
| 对库 similar_to 不变 | Task 6（复用 attach_similar） |
| 前端文案与操作集 | Task 3 |
| 不做项（可配阈值、gleaning、库内自动融合） | 不实现 |

## Placeholder scan

无 TBD/TODO 步骤；合并失败策略固定为「保留置信度最高一条」。
