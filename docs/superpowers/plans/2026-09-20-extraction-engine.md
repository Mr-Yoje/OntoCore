# 抽取引擎（引导约束 + 判重导入）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 单一 LLM 抽取路径：可选引导、按长度切块、向量初筛加一次精选判重、人审对象/关系时覆盖或新增或融合。

**Architecture:** 作业内顺序为解析 → `LlmExtractor`（提示只含勾选引导）→ `dedup.attach_similar` → 候选库。接受时 `ReviewService.accept_type` 按 `create` / `overwrite` / `merge` 写类型层。去掉 `hybrid` 与 `rules_only`。

**Tech Stack:** FastAPI、pytest、LiteLLM（`completion` + `embedding`）、Vite React vitest。假网关测抽取/精选/融合/嵌入。

**Spec:** `docs/superpowers/specs/2026-09-20-extraction-engine-design.md`

## Global Constraints

- 产品语言只用：对象、属性、关系、定义、实例、父对象。界面称稳定 id 为**编号**，不出现「IRI」一词。禁止：类、TBox、ABox、对象属性、数据属性、领域包。
- 内部仍用 IRI；前缀 `https://ontocore.local/ns/working#`。
- 新作业 `extractor` 固定为 `llm`。忽略客户端传入的抽取器三选一。
- 抽取必须选供应商与抽取模型；无 `rules_only` 离线路径。
- `extract` 提示不得包含未勾选的已有对象/关系。
- 判重只针对新对象和新关系；属性、实例不判重。
- 覆盖/融合写回已有编号；新增发新编号。覆盖对象=整份替换属性（未提到的已有属性删除）。
- 测试禁止打真实供应商。后端 `backend/tests/`，前端 `frontend` 下 `npm test`。
- 新行为先写失败测试再实现。提交用精简 Conventional Commits，默认提交 `main`。

---

## File structure

```
backend/src/ontocore/models.py
backend/src/ontocore/jobs/store.py
backend/src/ontocore/extract/llm.py
backend/src/ontocore/extract/ports.py
backend/src/ontocore/extract/chunking.py          # 新建
backend/src/ontocore/extract/guides.py            # 新建
backend/src/ontocore/extract/engine.py            # 新建，取代 llm_only 调用面
backend/src/ontocore/extract/dedup.py             # 新建
backend/src/ontocore/extract/registry.py
backend/src/ontocore/extract/llm_only.py          # 可改为 re-export 或删除，不得再被作业调用
backend/src/ontocore/extract/hybrid.py            # 删除
backend/src/ontocore/extract/rules_only.py        # 删除
backend/src/ontocore/jobs/service.py
backend/src/ontocore/review/service.py
backend/src/ontocore/ontology/repository.py
backend/src/ontocore/api/app.py
backend/tests/test_job_store.py                  # 新建或扩 test_review_and_jobs.py
backend/tests/test_extractors.py
backend/tests/test_dedup.py                       # 新建
backend/tests/test_review_and_jobs.py
backend/tests/test_api.py
backend/tests/test_fixture_regression.py
frontend/src/api.ts
frontend/src/pages/UploadPage.tsx
frontend/src/pages/ReviewPage.tsx
frontend/src/index.css
frontend/src/api.test.ts
README.md
docs/superpowers/specs/2026-09-15-ontocore-objects-relations-design.md
```

---

### Task 1: 作业记录引导与嵌入字段

**Files:**
- Modify: `backend/src/ontocore/jobs/store.py`
- Test: `backend/tests/test_review_and_jobs.py`（文件顶部追加测试）

**Interfaces:**
- Consumes: 现有 `JobStore.create(filename, extractor, model, *, provider_id, thinking)`
- Produces: `Job.embed_model: str | None`；`Job.guide_object_iris: list[str]`；`Job.guide_relation_iris: list[str]`；`Job.guide_instance_iris: list[str]`。SQLite `jobs` 增加 `embed_model TEXT`、`guide_object_iris TEXT NOT NULL DEFAULT '[]'`、`guide_relation_iris TEXT NOT NULL DEFAULT '[]'`、`guide_instance_iris TEXT NOT NULL DEFAULT '[]'`（JSON 数组）。旧库 `ALTER TABLE`。`create(..., *, embed_model=None, guide_object_iris=None, guide_relation_iris=None, guide_instance_iris=None)`。

- [ ] **Step 1: Write the failing test**

在 `backend/tests/test_review_and_jobs.py` 增加：

```python
def test_job_store_persists_guides_and_embed(tmp_path):
    from ontocore.jobs.store import JobStore
    from ontocore.constants import NS

    store = JobStore(str(tmp_path / "j.db"))
    job = store.create(
        "a.txt",
        "llm",
        "deepseek-chat",
        provider_id="p1",
        thinking=False,
        embed_model="embed-x",
        guide_object_iris=[f"{NS}Product"],
        guide_relation_iris=[],
        guide_instance_iris=[f"{NS}i1"],
    )
    loaded = store.get(job.id)
    assert loaded.extractor == "llm"
    assert loaded.embed_model == "embed-x"
    assert loaded.guide_object_iris == [f"{NS}Product"]
    assert loaded.guide_instance_iris == [f"{NS}i1"]
    assert loaded.guide_relation_iris == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_review_and_jobs.py::test_job_store_persists_guides_and_embed -v`

Expected: FAIL（`create()` 不接受 `embed_model` 或 `Job` 无该字段）

- [ ] **Step 3: Write minimal implementation**

`Job` 增加字段。`__init__` 里对缺失列 `ALTER TABLE`。`create`/`get`/`_row_to_job` 读写 JSON 列表；空则 `[]`；`embed_model` 空字符串存 `None`。

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/test_review_and_jobs.py::test_job_store_persists_guides_and_embed -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/ontocore/jobs/store.py backend/tests/test_review_and_jobs.py
git commit -m "feat: 作业记录引导编号与嵌入模型"
```

---

### Task 2: 候选 similar_to 与假网关队列

**Files:**
- Modify: `backend/src/ontocore/models.py`
- Modify: `backend/src/ontocore/extract/llm.py`
- Modify: `backend/src/ontocore/extract/ports.py`
- Modify: `backend/src/ontocore/extract/llm_only.py`（`result_from_dict` 忽略 LLM 返回的 `similar_to`）
- Test: `backend/tests/test_extractors.py`

**Interfaces:**
- Consumes: 现有 dataclass 候选
- Produces:
  - `SimilarRef(iri: str, label: str)`
  - `ObjectCandidateDraft.similar_to: list[SimilarRef] = field(default_factory=list)`
  - `RelationCandidateDraft.similar_to: list[SimilarRef] = field(default_factory=list)`
  - `ExtractionGuides` dataclass：`objects: list[dict]`、`attributes: list[dict]`、`relations: list[dict]`、`instances: list[dict]`；`as_prompt_dict() -> dict`
  - `LlmGateway.complete_structured` 不变；增加 `embed(self, texts: list[str]) -> list[list[float]]`
  - `FakeLlmGateway(canned: dict | list[dict], *, embeddings: dict[str, list[float]] | None = None, fail_embed: bool = False)`：`messages_log: list[list[dict]]`；队列耗尽或条目为 `{"__error__": true}` 时 `raise StructuredOutputError`；`embed` 按文本从 `embeddings` 取值，缺省 `[1.0, 0.0]`，`fail_embed` 时抛 `StructuredOutputError`

- [ ] **Step 1: Write the failing test**

```python
def test_fake_gateway_queues_and_logs_messages():
    from ontocore.extract.llm import FakeLlmGateway
    from ontocore.errors import StructuredOutputError

    gw = FakeLlmGateway([{"a": 1}, {"__error__": True}])
    assert gw.complete_structured({}, [{"role": "user", "content": "x"}]) == {"a": 1}
    assert gw.messages_log[0][0]["content"] == "x"
    try:
        gw.complete_structured({}, [])
        raise AssertionError("expected error")
    except StructuredOutputError:
        pass
    vec = FakeLlmGateway({}, embeddings={"保险产品": [1.0, 0.0]}).embed(["保险产品"])
    assert vec == [[1.0, 0.0]]
```

```python
def test_result_from_dict_drops_llm_similar_to():
    from ontocore.extract.llm_only import result_from_dict
    from ontocore.constants import NS

    result = result_from_dict({
        "object_candidates": [{
            "iri": f"{NS}Wait", "label": "等待期", "definition": "d",
            "parent_iri": None, "evidence": "e", "block_id": "b0", "confidence": 0.5,
            "similar_to": [{"iri": f"{NS}Other", "label": "x"}],
        }],
        "attribute_candidates": [],
        "relation_candidates": [],
        "instance_suggestions": [],
        "instance_rel_suggestions": [],
    })
    assert result.object_candidates[0].similar_to == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_extractors.py::test_fake_gateway_queues_and_logs_messages tests/test_extractors.py::test_result_from_dict_drops_llm_similar_to -v`

Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

在 `result_from_dict` 的 `_take` 之前对每个 item `dict(item)` 并 `pop("similar_to", None)`。`ObjectCandidateDraft`/`RelationCandidateDraft` 加 `similar_to`。扩展 `FakeLlmGateway` 与 Protocol。

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_extractors.py::test_fake_gateway_queues_and_logs_messages tests/test_extractors.py::test_result_from_dict_drops_llm_similar_to -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/ontocore/models.py backend/src/ontocore/extract/llm.py backend/src/ontocore/extract/ports.py backend/src/ontocore/extract/llm_only.py backend/tests/test_extractors.py
git commit -m "feat: 候选 similar_to 与假网关队列"
```

---

### Task 3: 单一抽取器、引导提示与切块

**Files:**
- Create: `backend/src/ontocore/extract/chunking.py`
- Create: `backend/src/ontocore/extract/guides.py`
- Create: `backend/src/ontocore/extract/engine.py`
- Modify: `backend/src/ontocore/extract/registry.py`
- Delete: `backend/src/ontocore/extract/hybrid.py`、`backend/src/ontocore/extract/rules_only.py`
- Modify: `backend/tests/test_extractors.py`、`backend/tests/test_fixture_regression.py`

**Interfaces:**
- Consumes: Task 2 的 `FakeLlmGateway`、`ExtractionGuides`、`result_from_dict`、`EXTRACTION_SCHEMA`
- Produces:
  - `SHORT_TEXT_LIMIT = 8000`
  - `def section_texts(doc: ParsedDocument) -> list[tuple[str, str]]` 返回 `(block_id, text)`。无 heading 则整篇一段 `block_id=""`。有 heading：标题前正文并入第一节；每节文本为块文本 `\n` 拼接。
  - `def extract_texts(doc: ParsedDocument) -> list[tuple[str, str]]`：`len(doc.full_text) <= 8000` 则 `[(first_id, doc.full_text)]`，否则 `section_texts(doc)`。
  - `def build_guides(snapshot: TypeSnapshot, *, object_iris: list[str], relation_iris: list[str], instances: list[dict]) -> ExtractionGuides`：只收录列出的对象（及其 `owner_iri` 在集合内的属性）和关系；`instances` 原样放入。
  - `class LlmExtractor`：`name = "llm"`；`extract(self, doc, snapshot, llm, *, guides: ExtractionGuides | None = None) -> ExtractionResult`。对 `extract_texts` 每段调用 `complete_structured`；`StructuredOutputError` 记 `BlockFailure(block_id, reason="抽取失败")` 并继续。合并五类列表与 `block_failures`。
  - 系统 content 固定为：`根据文档抽取对象（含属性）、关系和实例。guides 是软约束：实例含义接近引导中的对象或关系时对齐到其编号；确实无法对齐可以提议新对象、新属性、新关系。`
  - 用户 content 为 `json.dumps({"guides": guides.as_prompt_dict() if guides else {"objects": [], "attributes": [], "relations": [], "instances": []}, "filename": doc.filename, "text": section_text}, ensure_ascii=False)`。不得把 `snapshot` 全文放进提示。
  - `get_extractor("llm") -> LlmExtractor`。`get_extractor("hybrid"|"rules_only"|"llm_only")` 也返回同一实例（兼容测试 monkeypatch 前的名字），或只注册 `llm` 并改所有调用为 `"llm"`。本任务起作业与测试一律 `"llm"`。

- [ ] **Step 1: Write the failing tests**

```python
def test_extract_prompt_contains_only_selected_guides():
    from ontocore.constants import NS
    from ontocore.extract.engine import LlmExtractor
    from ontocore.extract.guides import build_guides
    from ontocore.extract.llm import FakeLlmGateway
    from ontocore.models import OntoObject, ParsedDocument, TextBlock, TypeSnapshot

    snap = TypeSnapshot(
        objects=(
            OntoObject(iri=f"{NS}Product", label="保险产品", definition="一种产品"),
            OntoObject(iri=f"{NS}Wait", label="等待期", definition="天数"),
        ),
        attributes=(),
        relations=(),
    )
    canned = {
        "object_candidates": [], "attribute_candidates": [], "relation_candidates": [],
        "instance_suggestions": [], "instance_rel_suggestions": [],
    }
    gw = FakeLlmGateway(canned)
    guides = build_guides(snap, object_iris=[f"{NS}Product"], relation_iris=[], instances=[])
    doc = ParsedDocument("a.txt", "短文", (TextBlock("b0", "paragraph", "短文"),))
    LlmExtractor().extract(doc, snap, gw, guides=guides)
    blob = gw.messages_log[0][1]["content"]
    assert "保险产品" in blob
    assert f"{NS}Product" in blob
    assert "等待期" not in blob


def test_long_doc_extracts_per_heading_and_keeps_other_chunks():
    from ontocore.extract.engine import LlmExtractor, SHORT_TEXT_LIMIT
    from ontocore.extract.llm import FakeLlmGateway
    from ontocore.models import ParsedDocument, TextBlock, TypeSnapshot

    pad = "字" * (SHORT_TEXT_LIMIT + 10)
    doc = ParsedDocument(
        "a.txt",
        pad,
        (
            TextBlock("b0", "heading", "第一节"),
            TextBlock("b1", "paragraph", "甲"),
            TextBlock("b2", "heading", "第二节"),
            TextBlock("b3", "paragraph", "乙"),
        ),
    )
    ok = {
        "object_candidates": [{
            "iri": "https://ontocore.local/ns/working#A", "label": "甲对象",
            "definition": "d", "parent_iri": None, "evidence": "甲",
            "block_id": "b0", "confidence": 0.5,
        }],
        "attribute_candidates": [], "relation_candidates": [],
        "instance_suggestions": [], "instance_rel_suggestions": [],
    }
    bad = {"object_candidates": [{"label": "残缺", "block_id": "b2"}],
           "attribute_candidates": [], "relation_candidates": [],
           "instance_suggestions": [], "instance_rel_suggestions": []}
    gw = FakeLlmGateway([ok, bad])
    result = LlmExtractor().extract(doc, TypeSnapshot(objects=(), attributes=(), relations=()), gw)
    assert len(gw.messages_log) == 2
    assert result.object_candidates[0].label == "甲对象"
    assert result.block_failures
```

把 `test_extractors.py` 里 hybrid/rules_only/llm_only 的 `get_extractor("...")` 改为 `LlmExtractor` 或 `get_extractor("llm")`。`test_extract_signature_has_no_domain_pack` 对 `LlmExtractor.extract`。删除 `test_rules_only_proposes_new_object_when_unaligned` 与 `test_hybrid_invalid_draft_becomes_block_failure`（切块非法草稿由上一测试覆盖）。

`test_fixture_regression.py`：用 `FakeLlmGateway` 返回至少一个 `object_candidates`，`get_extractor("llm").extract(...)`；不再调用 `rules_only`。空库 `create_app` 断言保留。

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_extractors.py tests/test_fixture_regression.py -v`

Expected: FAIL（无 `engine` 模块）

- [ ] **Step 3: Write minimal implementation**

实现 `chunking.py`、`guides.py`、`engine.py`。`registry.py` 仅 `{"llm": LlmExtractor()}`。删除 hybrid/rules_only 文件。全仓库 `get_extractor("hybrid"|"rules_only"|"llm_only")` 改为 `"llm"`。

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_extractors.py tests/test_fixture_regression.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/ontocore/extract backend/tests/test_extractors.py backend/tests/test_fixture_regression.py
git commit -m "feat: 单一 LLM 抽取并按长度切块"
```

---

### Task 4: 向量初筛与一次精选

**Files:**
- Create: `backend/src/ontocore/extract/dedup.py`
- Test: `backend/tests/test_dedup.py`

**Interfaces:**
- Consumes: `ExtractionResult`、`TypeSnapshot`、`LlmGateway.embed` / `complete_structured`、引导 IRI 列表
- Produces:
  - `def cosine(a: list[float], b: list[float]) -> float`
  - `def attach_similar(result: ExtractionResult, snapshot: TypeSnapshot, llm: LlmGateway, *, guide_object_iris: list[str], guide_relation_iris: list[str], use_embed: bool) -> None`（原地写 `similar_to`）
  - 对照集：snapshot 中 IRI 不在对应 guide 列表里的对象/关系。无新对象且无新关系、或对照为空：直接 return。
  - `use_embed=True`：对「显示名 + 空格 + 定义」调用 `llm.embed`；每条新对象对未勾选对象取 top 5；关系同理。`embed` 抛错则视为 `use_embed=False`。
  - `use_embed=False`：每条新项的对照为全部未勾选同类。
  - 然后 **一次** `complete_structured`。系统：`判断新建议与对照项是否同一含义。只输出确认为相似的已有编号。`
  - 用户 JSON：`{"new_objects":[{"key": iri, "label", "definition", "evidence", "candidates":[{"iri","label","definition"}]}], "new_relations":[...同结构...]}`
  - 期望输出：`{"object_similar": {"<new_iri>": ["<existing_iri>", ...]}, "relation_similar": {...}}`
  - 只把输出里出现且属于该条对照集的 IRI 写入 `SimilarRef`（label 从 snapshot 取）。精选抛 `StructuredOutputError` 时让调用方捕获（本函数不吞掉）。

- [ ] **Step 1: Write the failing tests**

```python
from ontocore.constants import NS
from ontocore.extract.dedup import attach_similar
from ontocore.extract.llm import FakeLlmGateway
from ontocore.models import (
    ExtractionResult, ObjectCandidateDraft, OntoObject, OntoRelation,
    RelationCandidateDraft, TypeSnapshot,
)


def _obj(iri, label, definition="d"):
    return ObjectCandidateDraft(
        iri=iri, label=label, definition=definition, parent_iri=None,
        evidence="e", block_id="b0", confidence=0.5,
    )


def test_embed_keeps_top_five_then_one_judge_call():
    existing = [
        OntoObject(iri=f"{NS}E{i}", label=f"已有{i}", definition="d")
        for i in range(6)
    ]
    snap = TypeSnapshot(objects=tuple(existing), attributes=(), relations=())
    result = ExtractionResult(
        object_candidates=[_obj(f"{NS}New", "新品")],
        attribute_candidates=[], relation_candidates=[],
        instance_suggestions=[], instance_rel_suggestions=[],
    )
    embeddings = {f"已有{i} d": [1.0, float(i)] for i in range(6)}
    embeddings["新品 d"] = [1.0, 0.0]
    judge = {"object_similar": {f"{NS}New": [f"{NS}E0"]}, "relation_similar": {}}
    gw = FakeLlmGateway(judge, embeddings=embeddings)
    attach_similar(
        result, snap, gw,
        guide_object_iris=[], guide_relation_iris=[], use_embed=True,
    )
    assert len(gw.messages_log) == 1
    payload = __import__("json").loads(gw.messages_log[0][1]["content"])
    assert len(payload["new_objects"][0]["candidates"]) == 5
    assert result.object_candidates[0].similar_to[0].iri == f"{NS}E0"


def test_no_embed_sends_all_unselected_to_judge():
    snap = TypeSnapshot(
        objects=(
            OntoObject(iri=f"{NS}Keep", label="引导对象", definition="d"),
            OntoObject(iri=f"{NS}Other", label="其它", definition="d"),
        ),
        attributes=(), relations=(),
    )
    result = ExtractionResult(
        object_candidates=[_obj(f"{NS}New", "新品")],
        attribute_candidates=[], relation_candidates=[],
        instance_suggestions=[], instance_rel_suggestions=[],
    )
    gw = FakeLlmGateway({"object_similar": {f"{NS}New": [f"{NS}Other"]}, "relation_similar": {}})
    attach_similar(
        result, snap, gw,
        guide_object_iris=[f"{NS}Keep"], guide_relation_iris=[], use_embed=False,
    )
    payload = __import__("json").loads(gw.messages_log[0][1]["content"])
    iris = {c["iri"] for c in payload["new_objects"][0]["candidates"]}
    assert f"{NS}Other" in iris
    assert f"{NS}Keep" not in iris
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_dedup.py -v`

Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

实现 `dedup.py`。零向量时 cosine 为 0。

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_dedup.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/ontocore/extract/dedup.py backend/tests/test_dedup.py
git commit -m "feat: 新对象关系向量初筛与一次精选"
```

---

### Task 5: 作业编排抽取与判重

**Files:**
- Modify: `backend/src/ontocore/jobs/service.py`
- Modify: `backend/src/ontocore/extract/llm.py`（`LiteLlmGateway.embed` 调 `litellm.embedding`，解析 `data[].embedding`）
- Modify: `backend/tests/test_review_and_jobs.py`
- Modify: `backend/src/ontocore/api/app.py`（仅 `JobService(...)` 传入 graph，若本任务需要；否则 Task 6 再改构造）

**Interfaces:**
- Consumes: `get_extractor("llm")`、`build_guides`、`attach_similar`、`Job` 引导字段、`OntologyRepository.snapshot`、`GraphRepository.instance_network`
- Produces: `JobService.__init__(self, jobs, candidates, ontology, llm_factory, graph)`。`run`：解析 → `build_guides`（实例：`instance_network()` 中 `onto_iri` 在 `guide_instance_iris` 的节点，dict 含 `iri/label/type_iri/data`）→ `extractor.extract(..., guides=guides)` → 若有新对象或新关系则 `attach_similar(..., use_embed=bool(job.embed_model))`；精选 `StructuredOutputError`：仍 `replace_job_results`，`set_status("partial", error="判重失败")`。块失败且有候选 → `partial`；全失败无候选 → `failed`；成功 → `completed`。`llm_factory(model, provider_id=..., thinking=...)` 用于抽取与精选（同一实例）。`use_embed` 时同一 factory 再 `factory(job.embed_model, provider_id=job.provider_id, thinking=False)` 若 embed 网关与 chat 分离；若 `FakeLlmGateway` 无第二实例，测试里 factory 对任意 model 返回同一 gw，且 gw 同时实现 `embed`。

- [ ] **Step 1: Write the failing tests**

```python
def test_job_extract_then_partial_on_judge_failure(tmp_path, monkeypatch):
    from ontocore.candidates.store import CandidateStore
    from ontocore.extract.llm import FakeLlmGateway
    from ontocore.jobs.service import JobService
    from ontocore.jobs.store import JobStore
    from ontocore.ontology.repository import OntologyRepository
    from ontocore.graph.memory import MemoryGraph
    from ontocore.constants import NS
    from ontocore.models import OntoObject

    ontology = OntologyRepository(str(tmp_path / "onto"))
    ontology.create_object(OntoObject(iri=f"{NS}Other", label="其它", definition="d"))
    extract_payload = {
        "object_candidates": [{
            "iri": f"{NS}New", "label": "新品", "definition": "d",
            "parent_iri": None, "evidence": "e", "block_id": "b0", "confidence": 0.5,
        }],
        "attribute_candidates": [], "relation_candidates": [],
        "instance_suggestions": [], "instance_rel_suggestions": [],
    }
    gw = FakeLlmGateway([extract_payload, {"__error__": True}])
    jobs = JobStore(str(tmp_path / "j.db"))
    cands = CandidateStore(str(tmp_path / "j.db"))
    service = JobService(jobs, cands, ontology, lambda *a, **k: gw, MemoryGraph())
    job = jobs.create("a.txt", "llm", "fake", guide_object_iris=[])
    done = service.run(job.id, "a.txt", "标题\n\n正文。".encode("utf-8"))
    assert done.status == "partial"
    assert "判重" in (done.error or "")
    rows = cands.list_type_candidates(job.id)
    assert rows[0].payload["label"] == "新品"
    assert rows[0].payload.get("similar_to") in ([], None)
```

把 `test_review_and_jobs.py` 里 `JobService(..., factory)` 补上 `MemoryGraph()`。`get_extractor` monkeypatch 改为补 `guides` kwargs（`extract(self, doc, snapshot, llm, **kwargs)`）。

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_review_and_jobs.py::test_job_extract_then_partial_on_judge_failure -v`

Expected: FAIL（`JobService` 参数或未调用判重）

- [ ] **Step 3: Write minimal implementation**

改 `JobService.run` 与构造。`LiteLlmGateway.embed`：

```python
def embed(self, texts: list[str]) -> list[list[float]]:
    import litellm
    try:
        response = litellm.embedding(model=self._model, input=texts, api_key=self._api_key or None, api_base=self._api_base or None)
    except Exception as exc:
        raise StructuredOutputError(str(exc)) from exc
    return [item["embedding"] for item in response.data]
```

（若 SDK 用属性访问则 `item.embedding`。）

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_review_and_jobs.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/ontocore/jobs/service.py backend/src/ontocore/extract/llm.py backend/src/ontocore/api/app.py backend/tests/test_review_and_jobs.py
git commit -m "feat: 作业内抽取后判重失败仍保留候选"
```

---

### Task 6: 接受时覆盖、新增、融合

**Files:**
- Modify: `backend/src/ontocore/ontology/repository.py`（`replace_object_bundle`、`replace_relation_payload`）
- Modify: `backend/src/ontocore/review/service.py`
- Test: `backend/tests/test_review_and_jobs.py`、必要时 `backend/tests/test_ontology_repository.py`

**Interfaces:**
- Consumes: `StoredTypeCandidate.payload`（含 `similar_to`）、`JobStore.get`、`llm_factory`
- Produces:
  - `OntologyRepository.replace_object_bundle(target_iri: str, *, label: str, definition: str, parent_iri: str | None, attributes: list[OntoAttribute]) -> None`：目标必须已存在。`update_object` 显示名/定义/父对象；删除 `snapshot.attributes` 中 `owner_iri == target_iri` 且 IRI 不在新列表的属性；新属性 `owner_iri` 改为 `target_iri`；已存在同 IRI 则 `update_attribute`，否则 `create_attribute`（新属性 IRI 若冲突则换新 local：保留抽取 IRI 仅当未占用）。
  - `OntologyRepository.replace_relation_payload(target_iri: str, *, label: str, definition: str, source_iri: str, target_object_iri: str) -> None`：更新显示名、定义，并替换 domain/range（清旧 `RDFS_DOMAIN`/`RDFS_RANGE` 再写）。
  - `ReviewService.__init__(..., llm_factory)`
  - `accept_type(self, candidate_id: str, *, mode: str = "create", target_iri: str | None = None) -> StoredTypeCandidate`
  - `kind == "attribute"`：忽略 mode，现有 `create_attribute`。非法 mode 对属性不报三种模式。
  - 对象/关系：`similar = payload.get("similar_to") or []`。无相似：仅允许 `mode in ("create", "")`，否则 `OntologyWriteError("无相似项时只能新增")`。有相似：`overwrite`/`merge` 必须 `target_iri` 属于 `similar` 的 iri 列表，否则 `OntologyWriteError("请选择要对齐的已有对象")`（关系文案「已有关系」）。`create` 忽略 target，走现有 create_*。
  - `overwrite` 对象：从同 job 的 `attribute` 候选中取 `owner_iri == payload["iri"]` 的 payload 组成属性列表，再 `replace_object_bundle`。关系：`replace_relation_payload`。
  - `merge`：`job = jobs.get(stored.job_id)`；`llm = llm_factory(job.model, provider_id=job.provider_id, thinking=job.thinking)`。对象用户 JSON 含 `existing`（目标当前对象+其自有属性）与 `incoming`（候选对象+同 job 归属属性）。系统：`合并为一条对象，必须保留新抽到的要点，编号保持已有编号。` 输出 `{"label","definition","parent_iri","attributes":[{"iri","label","definition","literal_kind"}]}`。写回 `replace_object_bundle`。关系输出 `{"label","definition","source_iri","target_iri"}`。`StructuredOutputError` 或缺字段 → `OntologyWriteError("融合失败")`，不写库。
  - 接受成功后 `set_type_status(..., "accepted")`；`register_type`。

- [ ] **Step 1: Write the failing tests**

```python
def test_accept_overwrite_replaces_object_attributes(tmp_path):
    from ontocore.candidates.store import CandidateStore
    from ontocore.constants import NS
    from ontocore.graph.memory import MemoryGraph
    from ontocore.graph.projector import Projector
    from ontocore.jobs.store import JobStore
    from ontocore.models import ExtractionResult, ObjectCandidateDraft, AttributeCandidateDraft, OntoObject, OntoAttribute
    from ontocore.ontology.repository import OntologyRepository
    from ontocore.review.service import ReviewService

    onto = OntologyRepository(str(tmp_path / "o"))
    onto.create_object(OntoObject(iri=f"{NS}Product", label="旧名", definition="旧定义"))
    onto.create_attribute(OntoAttribute(
        iri=f"{NS}oldAttr", label="旧属性", definition="x",
        owner_iri=f"{NS}Product", literal_kind="text",
    ))
    jobs = JobStore(str(tmp_path / "j.db"))
    cands = CandidateStore(str(tmp_path / "j.db"))
    job = jobs.create("a.txt", "llm", "fake")
    cands.replace_job_results(job.id, ExtractionResult(
        object_candidates=[ObjectCandidateDraft(
            iri=f"{NS}New", label="新名", definition="新定义", parent_iri=None,
            evidence="e", block_id="b0", confidence=0.9,
            similar_to=[{"iri": f"{NS}Product", "label": "旧名"}],
        )],
        attribute_candidates=[AttributeCandidateDraft(
            iri=f"{NS}newAttr", label="新属性", definition="y",
            owner_iri=f"{NS}New", literal_kind="text",
            evidence="e", block_id="b0", confidence=0.9,
        )],
        relation_candidates=[], instance_suggestions=[], instance_rel_suggestions=[],
    ))
    review = ReviewService(cands, onto, Projector(MemoryGraph()), jobs, MemoryGraph(), lambda *a, **k: None)
    oid = [r for r in cands.list_type_candidates(job.id) if r.kind == "object"][0].id
    review.accept_type(oid, mode="overwrite", target_iri=f"{NS}Product")
    snap = onto.snapshot()
    product = [o for o in snap.objects if o.iri == f"{NS}Product"][0]
    assert product.label == "新名"
    owned = [a for a in snap.attributes if a.owner_iri == f"{NS}Product"]
    assert {a.label for a in owned} == {"新属性"}


def test_accept_merge_writes_llm_result(tmp_path):
    from ontocore.candidates.store import CandidateStore
    from ontocore.constants import NS
    from ontocore.extract.llm import FakeLlmGateway
    from ontocore.graph.memory import MemoryGraph
    from ontocore.graph.projector import Projector
    from ontocore.jobs.store import JobStore
    from ontocore.models import ExtractionResult, ObjectCandidateDraft, OntoObject
    from ontocore.ontology.repository import OntologyRepository
    from ontocore.review.service import ReviewService

    onto = OntologyRepository(str(tmp_path / "o"))
    onto.create_object(OntoObject(iri=f"{NS}Product", label="旧名", definition="旧定义"))
    jobs = JobStore(str(tmp_path / "j.db"))
    cands = CandidateStore(str(tmp_path / "j.db"))
    job = jobs.create("a.txt", "llm", "fake")
    cands.replace_job_results(job.id, ExtractionResult(
        object_candidates=[ObjectCandidateDraft(
            iri=f"{NS}New", label="新名", definition="新定义", parent_iri=None,
            evidence="e", block_id="b0", confidence=0.9,
            similar_to=[{"iri": f"{NS}Product", "label": "旧名"}],
        )],
        attribute_candidates=[], relation_candidates=[],
        instance_suggestions=[], instance_rel_suggestions=[],
    ))
    gw = FakeLlmGateway({
        "label": "融合名", "definition": "融合定义", "parent_iri": None,
        "attributes": [],
    })
    graph = MemoryGraph()
    review = ReviewService(cands, onto, Projector(graph), jobs, graph, lambda *a, **k: gw)
    oid = [r for r in cands.list_type_candidates(job.id) if r.kind == "object"][0].id
    review.accept_type(oid, mode="merge", target_iri=f"{NS}Product")
    assert [o.label for o in onto.snapshot().objects if o.iri == f"{NS}Product"] == ["融合名"]
```

`test_accept_object_then_project` 改为 `JobService`/`ReviewService` 新构造签名，`accept_type` 无相似即默认新增。

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_review_and_jobs.py::test_accept_overwrite_replaces_object_attributes tests/test_review_and_jobs.py::test_accept_merge_writes_llm_result -v`

Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

实现 repository 两个 replace 方法与 `accept_type` 分支。`similar_to` 从 payload 读 list[dict]。

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_review_and_jobs.py tests/test_ontology_repository.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/ontocore/ontology/repository.py backend/src/ontocore/review/service.py backend/tests/test_review_and_jobs.py backend/tests/test_ontology_repository.py
git commit -m "feat: 对象关系接受支持覆盖新增融合"
```

---

### Task 7: HTTP 作业与接受接口

**Files:**
- Modify: `backend/src/ontocore/api/app.py`
- Modify: `backend/tests/test_api.py`

**Interfaces:**
- Consumes: Task 1 `jobs.create` 新参数、Task 5 `JobService`、Task 6 `accept_type`
- Produces:
  - `POST /api/jobs`：`provider_id`、`model` 必填；缺则 400 `请选择供应商` / `请选择具体模型`。`extractor` 表单可忽略。`embed_model: str | None = Form(None)`。`guide_object_iris`/`guide_relation_iris`/`guide_instance_iris` 为重复表单字段或 JSON 字符串（选一种：重复 `Form(None)` 列表 `list[str] | None`）。`jobs.create(..., extractor="llm", embed_model=..., guide_*=...)`。
  - `create_app`：`JobService(..., graph_repo)`，`ReviewService(..., llm_factory=factory)`。
  - `POST /api/type-candidates/{id}/accept`：可选 JSON `{"mode": "create"|"overwrite"|"merge", "target_iri": str | null}`。空 body 视为 `create`。调用 `review.accept_type(...)`。

- [ ] **Step 1: Write the failing tests**

改 `test_post_jobs_extractor_error_is_not_500`：先 `PUT /api/settings` 一个供应商，再 POST file + `provider_id` + `model`，monkeypatch `JobService.run` 或 extractor 仍失败，断言 200/`failed`。

新增：

```python
def test_create_job_requires_provider_and_stores_guides(tmp_path, monkeypatch):
    from ontocore.jobs.service import JobService
    monkeypatch.setattr(JobService, "run", lambda self, job_id, filename, data: self._jobs.set_status(job_id, "completed"))
    client = TestClient(create_app(data_dir=tmp_path))
    client.put("/api/settings", json={"providers": [{
        "label": "DeepSeek", "prefix": "deepseek",
        "api_base": "https://api.deepseek.com", "api_key": "sk", "model": "deepseek-chat",
    }]})
    pid = client.get("/api/settings").json()["providers"][0]["id"]
    missing = client.post("/api/jobs", files={"file": ("a.txt", b"hi", "text/plain")})
    assert missing.status_code == 400
    r = client.post(
        "/api/jobs",
        files={"file": ("a.txt", b"hi", "text/plain")},
        data={"provider_id": pid, "model": "deepseek-chat", "guide_object_iris": "https://ontocore.local/ns/working#Product"},
    )
    assert r.status_code == 200
    assert r.json()["extractor"] == "llm"
    assert "https://ontocore.local/ns/working#Product" in r.json()["guide_object_iris"]
```

接受接口测可放 `test_review_and_jobs` 已覆盖则 API 层只测 JSON 传入 `mode`（TestClient + 内存夹具较重，可用 monkeypatch `ReviewService.accept_type` 捕获 kwargs）。

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_api.py -v`

Expected: FAIL（仍默认 hybrid / rules_only 免模型）

- [ ] **Step 3: Write minimal implementation**

改 `create_job` 与 `accept_type_candidate`。Pydantic body：

```python
class AcceptBody(BaseModel):
    mode: str = "create"
    target_iri: str | None = None
```

`request: Request` 读 JSON，空则默认。

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_api.py tests/test_review_and_jobs.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/ontocore/api/app.py backend/tests/test_api.py
git commit -m "feat: 作业接口固定 llm 并支持三种接受模式"
```

---

### Task 8: 上传引导弹层与审阅导入对话框

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/pages/UploadPage.tsx`
- Modify: `frontend/src/pages/ReviewPage.tsx`
- Modify: `frontend/src/index.css`（沿用现有 `modal-backdrop` / `role="dialog"`）
- Modify: `frontend/src/api.test.ts`
- Modify: `README.md`（去掉 hybrid/rules_only 说明）
- Modify: `docs/superpowers/specs/2026-09-15-ontocore-objects-relations-design.md` 上传/默认抽取/数据流与本实现一致的句子（抽取引擎已指向 2026-09-20）

**Interfaces:**
- Consumes: `GET /api/objects`、`GET /api/relations`、`GET /api/graph/network`、Task 7 表单字段与 accept JSON
- Produces:
  - `api.createJob(file, { provider_id, model, thinking, embed_model?, guide_object_iris, guide_relation_iris, guide_instance_iris })` 不再传抽取器。
  - `api.acceptType(id, body?: { mode: string; target_iri?: string | null })`
  - 上传页：无 hybrid/llm_only/rules_only。供应商、具体模型、thinking、嵌入模型（同一 `models` 列表，可空选项「不使用嵌入」）。按钮「选择引导」，旁已选数量。弹层 `role="dialog"`：搜索框；对象（`parent_iri` 缩进列表即可，不必真树控件）、关系、实例（`onto_label` + 所属 `type_iri` 显示名）。多选、清空、确定。文案不用「IRI」。
  - 审阅：`payload.similar_to` 非空时显示「与{label}相似」。点接受：无相似则 `acceptType(id)`；有相似则对话框选目标 + 覆盖/新增/融合，确认后 `acceptType(id, { mode, target_iri })`。属性行永不打开该对话框。

- [ ] **Step 1: Write the failing tests**

`frontend/src/api.test.ts`：

```javascript
  it("upload page selects guides not extractors", () => {
    const t = readFileSync("src/pages/UploadPage.tsx", "utf8");
    expect(t.includes("hybrid")).toBe(false);
    expect(t.includes("rules_only")).toBe(false);
    expect(t.includes("llm_only")).toBe(false);
    expect(t.includes("选择引导")).toBe(true);
    expect(t.includes("guide_object_iris")).toBe(true);
    expect(t.includes("embed_model")).toBe(true);
    expect(t.includes("不使用嵌入")).toBe(true);
  });

  it("review page import modes when similar", () => {
    const t = readFileSync("src/pages/ReviewPage.tsx", "utf8");
    expect(t.includes("similar_to")).toBe(true);
    expect(t.includes("覆盖")).toBe(true);
    expect(t.includes("新增")).toBe(true);
    expect(t.includes("融合")).toBe(true);
    expect(t.includes("acceptType")).toBe(true);
    expect(t.includes("target_iri")).toBe(true);
  });
```

改现有 `upload page picks vendor and model`，删除对抽取器 select 的隐含依赖。

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test`

Working directory: `frontend`。Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

改 `api.ts`、`UploadPage.tsx`、`ReviewPage.tsx`。引导弹层用已有 Dialog 模式（参考本体页 `role="dialog"` + `modal-backdrop`）。`createJob` 对每个 IRI `form.append("guide_object_iris", iri)`（与后端 `list[str] = Form(default=[])` 对齐；若 Task 7 用 JSON 字符串则这里 `JSON.stringify`）。

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm test`（`frontend`）

Expected: PASS

然后打开 http://localhost:5173/ 上传页：无三种抽取器，能开「选择引导」；审阅页有相似文案与三种模式（无后端数据时至少 UI 分支通过代码存在性测试；有后端则走主路径点开弹层）。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api.ts frontend/src/pages/UploadPage.tsx frontend/src/pages/ReviewPage.tsx frontend/src/index.css frontend/src/api.test.ts README.md docs/superpowers/specs/2026-09-15-ontocore-objects-relations-design.md
git commit -m "feat: 上传引导选择与审阅三种导入"
```

---

## Self-review (spec coverage)

| 规格 | 任务 |
| --- | --- |
| 去掉 hybrid/rules_only，作业 `llm` | 3, 7, 8 |
| 引导只进抽取提示 | 3 |
| 短文 8000 / 长文切块多次 | 3 |
| 向量 top5 + 一次精选；无嵌入全量未勾选 | 4, 5 |
| 精选失败 partial 保留候选 | 5 |
| similar_to 展示；三种导入 | 6, 7, 8 |
| 覆盖整份属性；融合一次 LLM 写回编号 | 6 |
| 属性/实例无三种模式 | 6, 8 |
| 上传弹层 + 可选嵌入 | 8 |
| 假 LLM/嵌入、禁止真网 | 全程测试 |
| LiteLLM embeddings | 5 |
| 2026-09-15 上传条款 | 8 |

无 TBD。`accept_type` / `Job.guide_*` / `LlmExtractor.extract(..., guides=)` / `attach_similar` 名称前后任务一致。
