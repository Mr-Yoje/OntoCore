# OntoCore 对象与关系本体 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建成可演示的 OntoCore：空库维护对象/属性/关系并展示类型关系网；上传说明书抽取后只审类型候选；一键投影实例到图并展示实例关系网；OWL 导入导出；无领域包。

**Architecture:** Python 模块化单体（FastAPI）+ TypeScript Web。类型层权威为 Oxigraph 中的 OWL 小剖面（对外只暴露对象/属性/关系）；实例只进图（Neo4j 或内存）。抽取器只读类型快照，不得写权威库或图。无领域包、无种子。

**Tech Stack:** Python 3.12、FastAPI、pyoxigraph、SQLite、neo4j 驱动、LiteLLM、pypdf、python-docx、pytest；前端 Vite + React + TypeScript。

**Spec:** `docs/superpowers/specs/2026-09-10-ontocore-objects-relations-design.md`（实现以此为准；旧规格不改、不实现领域包）。

## Global Constraints

- 工作本体 id 固定 `working`；IRI 前缀 `https://ontocore.local/ns/working#`。
- 类型层权威存 RDF/OWL 小剖面；实例只进图；图不可用时不得把实例写入 OWL。
- 产品语言（API JSON 字段名、前端文案、错误信息）只用：对象、属性、关系、定义、实例、父对象。禁止出现：类、TBox、ABox、对象属性、数据属性、领域包。
- 对象 → `owl:Class`；定义 → `rdfs:comment`；父对象 → 单一 `rdfs:subClassOf` IRI；属性 → `owl:DatatypeProperty`（domain=所属对象，range=xsd:string|decimal|date）；关系 → `owl:ObjectProperty`（恰好一个 domain、一个 range）。
- 属性字面量类型仅 `text` / `number` / `date`。关系禁止多起点或多终点。
- 子对象只读继承祖先属性与关系；禁止多继承；禁止子对象覆盖同名属性。
- OWL 另允许可选两个命名类 `owl:disjointWith`。禁止复杂匿名类、空白 `rdfs:subClassOf`、全量 OWL 2 DL。
- 导出/导入：Turtle 与 JSON-LD；导入同 IRI 默认拒绝，除非 `force=true`。第一期不提供改 IRI。
- 抽取器签名为 `extract(doc, snapshot, llm)`，无领域包参数；不得写类型层或图。
- 类型候选状态仅 `proposed` / `accepted` / `rejected`。建议实例状态仅 `proposed` / `projected` / `skipped`。无人审实例。
- LLM 只经 `complete_structured`；抽取器内禁止直连厂商 SDK。
- 默认抽取器 `hybrid`；内置 `llm_only`；实现最小 `rules_only`（通用标题启发式 + 当前对象显示名匹配，无 LLM）。
- 图节点/边写 `onto_iri`、`onto_label`；内存/Neo4j 原生 label 固定 `OntoNode` / `ONTO_REL`，同步不改原生 label。
- 作业状态：`queued`、`running`、`failed`、`partial`、`completed`、`types_accepted_graph_pending`。
- 空库启动：不加载任何种子 Turtle；无 `ontocore/domain` 包。
- 第一期不做 OCR、准确率 CI、多租户、实例逐条审阅、关系多端点。

---

## File structure

```
backend/pyproject.toml
backend/src/ontocore/__init__.py
backend/src/ontocore/constants.py
backend/src/ontocore/errors.py
backend/src/ontocore/models.py
backend/src/ontocore/ontology/profile.py
backend/src/ontocore/ontology/repository.py
backend/src/ontocore/candidates/store.py
backend/src/ontocore/graph/ports.py
backend/src/ontocore/graph/memory.py
backend/src/ontocore/graph/neo4j_repo.py
backend/src/ontocore/graph/projector.py
backend/src/ontocore/extract/ingress.py
backend/src/ontocore/extract/llm.py
backend/src/ontocore/extract/ports.py
backend/src/ontocore/extract/llm_only.py
backend/src/ontocore/extract/hybrid.py
backend/src/ontocore/extract/rules_only.py
backend/src/ontocore/extract/registry.py
backend/src/ontocore/jobs/store.py
backend/src/ontocore/jobs/service.py
backend/src/ontocore/review/service.py
backend/src/ontocore/settings.py
backend/src/ontocore/api/app.py
backend/tests/fixtures/sample.txt
backend/tests/test_*.py
frontend/package.json
frontend/src/App.tsx
frontend/src/api.ts
frontend/src/pages/OntologyPage.tsx
frontend/src/pages/UploadPage.tsx
frontend/src/pages/ReviewPage.tsx
frontend/src/pages/GraphPage.tsx
frontend/src/pages/SettingsPage.tsx
frontend/src/components/TypeNetwork.tsx
frontend/src/components/InstanceNetwork.tsx
docker-compose.yml
README.md
```

禁止创建 `backend/src/ontocore/domain/`。

---

### Task 1: 常量、错误、共享模型、OWL 剖面校验

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/src/ontocore/__init__.py`
- Create: `backend/src/ontocore/constants.py`
- Create: `backend/src/ontocore/errors.py`
- Create: `backend/src/ontocore/models.py`
- Create: `backend/src/ontocore/ontology/__init__.py`
- Create: `backend/src/ontocore/ontology/profile.py`
- Test: `backend/tests/test_profile.py`

**Interfaces:**
- Consumes: 无
- Produces: `ONTOLOGY_ID`, `NS`, `ProfileViolation`, `OntologyWriteError`, `ConflictError`, `OntoObject`, `OntoAttribute`, `OntoRelation`, `TypeSnapshot`, `assert_profile_turtle(ttl: str) -> None`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_profile.py
from ontocore.constants import NS
from ontocore.errors import ProfileViolation
from ontocore.ontology.profile import assert_profile_turtle


def test_named_object_hierarchy_ok():
    ttl = f"""
    @prefix : <{NS}> .
    @prefix owl: <http://www.w3.org/2002/07/owl#> .
    @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
    :Product a owl:Class ; rdfs:label "保险产品" ; rdfs:comment "一种保险产品" .
    :Critical a owl:Class ; rdfs:subClassOf :Product ; rdfs:label "重疾险" .
    """
    assert_profile_turtle(ttl)


def test_blank_restriction_rejected():
    ttl = f"""
    @prefix : <{NS}> .
    @prefix owl: <http://www.w3.org/2002/07/owl#> .
    @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
    :Product a owl:Class .
    :Product rdfs:subClassOf [ a owl:Restriction ; owl:onProperty :p ; owl:someValuesFrom :Coverage ] .
    """
    try:
        assert_profile_turtle(ttl)
    except ProfileViolation:
        return
    raise AssertionError("expected ProfileViolation")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend; python -m pytest tests/test_profile.py -v`

Expected: FAIL with `ModuleNotFoundError` or cannot import `ontocore`

- [ ] **Step 3: Write minimal implementation**

`backend/pyproject.toml`:

```toml
[project]
name = "ontocore"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115",
  "uvicorn>=0.32",
  "python-multipart>=0.0.12",
  "pyoxigraph>=0.4",
  "neo4j>=5.26",
  "litellm>=1.55",
  "pydantic>=2.10",
  "pypdf>=5.1",
  "python-docx>=1.1",
]

[project.optional-dependencies]
dev = ["pytest>=8.3", "httpx>=0.28"]

[build-system]
requires = ["setuptools>=75"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
```

`constants.py`:

```python
ONTOLOGY_ID = "working"
NS = "https://ontocore.local/ns/working#"
XSD = "http://www.w3.org/2001/XMLSchema#"
LITERAL_RANGE = {
    "text": f"{XSD}string",
    "number": f"{XSD}decimal",
    "date": f"{XSD}date",
}
RANGE_LITERAL = {v: k for k, v in LITERAL_RANGE.items()}
```

`errors.py`: `ProfileViolation`、`OntologyWriteError`、`ConflictError`、`IngressError`、`GraphUnavailable`、`StructuredOutputError`。均为 `Exception` 子类。`ConflictError` 带 `message: str`。

`models.py`（后续任务必须原样使用这些名字）：

```python
from dataclasses import dataclass, field
from typing import Any, Literal

LiteralKind = Literal["text", "number", "date"]
TypeCandidateKind = Literal["object", "attribute", "relation"]
TypeCandidateStatus = Literal["proposed", "accepted", "rejected"]
InstanceCandidateStatus = Literal["proposed", "projected", "skipped"]
JobStatus = Literal[
    "queued", "running", "failed", "partial", "completed",
    "types_accepted_graph_pending",
]

@dataclass(frozen=True)
class OntoObject:
    iri: str
    label: str
    definition: str
    parent_iri: str | None = None

@dataclass(frozen=True)
class OntoAttribute:
    iri: str
    label: str
    definition: str
    owner_iri: str
    literal_kind: LiteralKind

@dataclass(frozen=True)
class OntoRelation:
    iri: str
    label: str
    definition: str
    source_iri: str
    target_iri: str

@dataclass(frozen=True)
class TypeSnapshot:
    objects: tuple[OntoObject, ...]
    attributes: tuple[OntoAttribute, ...]
    relations: tuple[OntoRelation, ...]

@dataclass(frozen=True)
class TypeNetworkNode:
    iri: str
    label: str
    definition: str
    parent_iri: str | None

@dataclass(frozen=True)
class TypeNetworkEdge:
    iri: str
    label: str
    source_iri: str
    target_iri: str

@dataclass(frozen=True)
class TypeNetwork:
    nodes: tuple[TypeNetworkNode, ...]
    edges: tuple[TypeNetworkEdge, ...]

@dataclass(frozen=True)
class TextBlock:
    block_id: str
    kind: Literal["heading", "paragraph", "list"]
    text: str

@dataclass(frozen=True)
class ParsedDocument:
    filename: str
    full_text: str
    blocks: tuple[TextBlock, ...]

@dataclass
class ObjectCandidateDraft:
    iri: str
    label: str
    definition: str
    parent_iri: str | None
    evidence: str
    block_id: str
    confidence: float

@dataclass
class AttributeCandidateDraft:
    iri: str
    label: str
    definition: str
    owner_iri: str
    literal_kind: LiteralKind
    evidence: str
    block_id: str
    confidence: float

@dataclass
class RelationCandidateDraft:
    iri: str
    label: str
    definition: str
    source_iri: str
    target_iri: str
    evidence: str
    block_id: str
    confidence: float

@dataclass
class InstanceSuggestionDraft:
    local_id: str
    type_iri: str
    label: str
    data: dict[str, Any]
    evidence: str
    block_id: str
    confidence: float

@dataclass
class InstanceRelDraft:
    source_local_id: str
    target_local_id: str
    predicate_iri: str
    evidence: str
    block_id: str
    confidence: float

@dataclass
class BlockFailure:
    block_id: str
    reason: str

@dataclass
class ExtractionResult:
    object_candidates: list[ObjectCandidateDraft]
    attribute_candidates: list[AttributeCandidateDraft]
    relation_candidates: list[RelationCandidateDraft]
    instance_suggestions: list[InstanceSuggestionDraft]
    instance_rel_suggestions: list[InstanceRelDraft]
    block_failures: list[BlockFailure] = field(default_factory=list)
```

`profile.py`：用 `pyoxigraph.Store` 解析 Turtle；若存在 `owl:Restriction` 或空白节点作为 `rdfs:subClassOf` 对象，抛 `ProfileViolation`。允许 `owl:Class`、`owl:ObjectProperty`、`owl:DatatypeProperty`、IRI 父类、`rdfs:domain`/`range`、IRI 两端的 `owl:disjointWith`。

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend; python -m pip install -e ".[dev]"; python -m pytest tests/test_profile.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/pyproject.toml backend/src/ontocore backend/tests/test_profile.py
git commit -m "feat: add OWL profile validator and object-relation models"
```

---

### Task 2: OntologyRepository（Oxigraph）对象/属性/关系 CRUD 与导入导出

**Files:**
- Create: `backend/src/ontocore/ontology/repository.py`
- Test: `backend/tests/test_ontology_repository.py`

**Interfaces:**
- Consumes: `OntoObject`, `OntoAttribute`, `OntoRelation`, `TypeSnapshot`, `TypeNetwork`, `assert_profile_turtle`, `OntologyWriteError`, `NS`, `LITERAL_RANGE`, `RANGE_LITERAL`
- Produces:

```python
class OntologyRepository:
    def __init__(self, path: str | None = None) -> None: ...
    def snapshot(self) -> TypeSnapshot: ...
    def type_network(self) -> TypeNetwork: ...
    def create_object(self, item: OntoObject) -> None: ...
    def update_object(self, iri: str, *, label: str | None = None, definition: str | None = None, parent_iri: str | None | object = ...) -> None: ...
    def delete_object(self, iri: str) -> None: ...
    def create_attribute(self, item: OntoAttribute) -> None: ...
    def update_attribute(self, iri: str, *, label: str | None = None, definition: str | None = None, literal_kind: LiteralKind | None = None) -> None: ...
    def delete_attribute(self, iri: str) -> None: ...
    def create_relation(self, item: OntoRelation) -> None: ...
    def update_relation(self, iri: str, *, label: str | None = None, definition: str | None = None) -> None: ...
    def delete_relation(self, iri: str) -> None: ...
    def inherited_attributes(self, object_iri: str) -> list[OntoAttribute]: ...
    def inherited_relations(self, object_iri: str) -> list[OntoRelation]: ...
    def export_turtle(self) -> str: ...
    def export_jsonld(self) -> str: ...
    def import_turtle(self, ttl: str, *, force: bool = False) -> None: ...
    def has_iri(self, iri: str) -> bool: ...
```

约定：`update_object` 的 `parent_iri` 用哨兵区分「不改」与「改为 None」。同一时刻仅一个写事务：`threading.RLock()`。空库 `snapshot()` 与 `type_network()` 均为空。`create_object`：父对象非空且不存在 → `OntologyWriteError`；IRI 已存在 → `OntologyWriteError`；已有父对象时不得再设第二个父（单 `rdfs:subClassOf`）。`create_attribute`：`owner_iri` 必须已是对象。`create_relation`：`source_iri` 与 `target_iri` 必须已是对象；不得写入第二个 domain 或 range。`delete_object`：若有子对象、或以它为端点的关系、或挂在它上的属性 → `OntologyWriteError`（实例占用由后续 Graph 任务在服务层查，仓库本层先拦类型层引用）。`inherited_attributes`：沿父链收集，子对象自身属性与祖先属性同 `label` 则 `OntologyWriteError` 禁止创建。`import_turtle`：先 `assert_profile_turtle`；无 force 时 IRI 交集非空 → `OntologyWriteError`。启动时**不得**调用 import。`export_jsonld` 用 pyoxigraph serialize `application/ld+json`，不行则手写含 IRI 字符串的 `@graph`。

- [ ] **Step 1: Write the failing test**

```python
from ontocore.constants import NS
from ontocore.errors import OntologyWriteError
from ontocore.models import OntoAttribute, OntoObject, OntoRelation
from ontocore.ontology.repository import OntologyRepository


def test_empty_start():
    repo = OntologyRepository()
    assert repo.snapshot().objects == ()
    assert repo.type_network().nodes == ()


def test_create_object_and_network():
    repo = OntologyRepository()
    repo.create_object(OntoObject(iri=f"{NS}Product", label="保险产品", definition="一种产品"))
    repo.create_object(OntoObject(iri=f"{NS}Coverage", label="保险责任", definition="一条责任"))
    repo.create_relation(OntoRelation(
        iri=f"{NS}contains", label="包含", definition="产品包含责任",
        source_iri=f"{NS}Product", target_iri=f"{NS}Coverage",
    ))
    net = repo.type_network()
    assert {n.label for n in net.nodes} == {"保险产品", "保险责任"}
    assert net.edges[0].source_iri.endswith("Product")
    assert net.edges[0].target_iri.endswith("Coverage")


def test_parent_and_inherited_attribute():
    repo = OntologyRepository()
    repo.create_object(OntoObject(iri=f"{NS}Product", label="保险产品", definition="d"))
    repo.create_attribute(OntoAttribute(
        iri=f"{NS}name", label="名称", definition="显示名", owner_iri=f"{NS}Product", literal_kind="text",
    ))
    repo.create_object(OntoObject(iri=f"{NS}Critical", label="重疾险", definition="d", parent_iri=f"{NS}Product"))
    inherited = repo.inherited_attributes(f"{NS}Critical")
    assert any(a.label == "名称" for a in inherited)


def test_missing_parent_rejected():
    repo = OntologyRepository()
    try:
        repo.create_object(OntoObject(iri=f"{NS}A", label="A", definition="d", parent_iri=f"{NS}Missing"))
    except OntologyWriteError:
        return
    raise AssertionError("expected OntologyWriteError")


def test_relation_unknown_endpoint_rejected():
    repo = OntologyRepository()
    repo.create_object(OntoObject(iri=f"{NS}Product", label="产品", definition="d"))
    try:
        repo.create_relation(OntoRelation(
            iri=f"{NS}contains", label="包含", definition="d",
            source_iri=f"{NS}Product", target_iri=f"{NS}Coverage",
        ))
    except OntologyWriteError:
        return
    raise AssertionError("expected OntologyWriteError")


def test_import_same_iri_rejected_without_force():
    repo = OntologyRepository()
    repo.create_object(OntoObject(iri=f"{NS}Product", label="保险产品", definition="d"))
    ttl = repo.export_turtle()
    try:
        repo.import_turtle(ttl, force=False)
    except OntologyWriteError:
        return
    raise AssertionError("expected OntologyWriteError")


def test_import_force_overwrites_label():
    repo = OntologyRepository()
    repo.create_object(OntoObject(iri=f"{NS}Product", label="旧", definition="d"))
    ttl = (
        f"@prefix : <{NS}> . @prefix owl: <http://www.w3.org/2002/07/owl#> . "
        f"@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . "
        f':Product a owl:Class ; rdfs:label "新" ; rdfs:comment "d" .'
    )
    repo.import_turtle(ttl, force=True)
    labels = {c.iri: c.label for c in repo.snapshot().objects}
    assert labels[f"{NS}Product"] == "新"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend; python -m pytest tests/test_ontology_repository.py -v`

Expected: FAIL cannot import `OntologyRepository`

- [ ] **Step 3: Write minimal implementation**

Oxigraph `Store`：`path is None` 用内存，否则目录。`create_object` 写 `owl:Class`、`rdfs:label`、`rdfs:comment`、可选 `rdfs:subClassOf`。`create_attribute` 写 `owl:DatatypeProperty` + domain + `LITERAL_RANGE[literal_kind]`。`create_relation` 写 `owl:ObjectProperty` + 单一 domain/range。`type_network`：节点来自对象，边来自关系（source→target）。`delete_object` 查询子类、属性 domain、关系 domain/range，有则抛错。

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend; python -m pytest tests/test_ontology_repository.py tests/test_profile.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/ontocore/ontology/repository.py backend/tests/test_ontology_repository.py
git commit -m "feat: add ontology repository for objects, attributes, and relations"
```

---

### Task 3: SQLite CandidateStore

**Files:**
- Create: `backend/src/ontocore/candidates/__init__.py`
- Create: `backend/src/ontocore/candidates/store.py`
- Test: `backend/tests/test_candidate_store.py`

**Interfaces:**
- Consumes: `ExtractionResult`, `TypeCandidateStatus`, `InstanceCandidateStatus`
- Produces:

```python
@dataclass
class StoredTypeCandidate:
    id: str
    kind: TypeCandidateKind
    job_id: str
    status: TypeCandidateStatus
    payload: dict

@dataclass
class StoredInstanceCandidate:
    id: str
    kind: Literal["instance", "instance_rel"]
    job_id: str
    status: InstanceCandidateStatus
    payload: dict

class CandidateStore:
    def __init__(self, sqlite_path: str) -> None: ...
    def replace_job_results(self, job_id: str, result: ExtractionResult) -> None: ...
    def list_type_candidates(self, job_id: str) -> list[StoredTypeCandidate]: ...
    def list_instance_candidates(self, job_id: str) -> list[StoredInstanceCandidate]: ...
    def get_type(self, candidate_id: str) -> StoredTypeCandidate: ...
    def set_type_status(self, candidate_id: str, status: TypeCandidateStatus) -> StoredTypeCandidate: ...
    def set_instance_status(self, candidate_id: str, status: InstanceCandidateStatus) -> StoredInstanceCandidate: ...
```

`set_type_status` 只允许类型行。`set_instance_status` 只允许实例行。不提供把实例设为 `accepted` 的 API。`replace_job_results` 删该 job 旧行后插入，id 用 UUID。类型行 status=`proposed`；实例行 status=`proposed`。

- [ ] **Step 1: Write the failing test**

```python
from ontocore.candidates.store import CandidateStore
from ontocore.models import ExtractionResult, ObjectCandidateDraft


def test_type_accept_and_instance_not_accepted(tmp_path):
    store = CandidateStore(str(tmp_path / "c.db"))
    result = ExtractionResult(
        object_candidates=[ObjectCandidateDraft(
            iri="https://ontocore.local/ns/working#Foo", label="Foo", definition="",
            parent_iri=None, evidence="原文", block_id="b1", confidence=0.9,
        )],
        attribute_candidates=[],
        relation_candidates=[],
        instance_suggestions=[],
        instance_rel_suggestions=[],
    )
    store.replace_job_results("job1", result)
    rows = store.list_type_candidates("job1")
    assert rows[0].status == "proposed"
    updated = store.set_type_status(rows[0].id, "accepted")
    assert updated.status == "accepted"
    assert store.list_instance_candidates("job1") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend; python -m pytest tests/test_candidate_store.py -v`

Expected: FAIL cannot import `CandidateStore`

- [ ] **Step 3: Write minimal implementation**

表 `candidates(id TEXT PRIMARY KEY, job_id TEXT, layer TEXT, kind TEXT, status TEXT, payload_json TEXT)`。`layer` 为 `type` 或 `instance`。

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend; python -m pytest tests/test_candidate_store.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/ontocore/candidates backend/tests/test_candidate_store.py
git commit -m "feat: add candidate store with type review and instance projection states"
```

---

### Task 4: 内存图、Projector、显示名同步、删除实例

**Files:**
- Create: `backend/src/ontocore/graph/__init__.py`
- Create: `backend/src/ontocore/graph/ports.py`
- Create: `backend/src/ontocore/graph/memory.py`
- Create: `backend/src/ontocore/graph/projector.py`
- Test: `backend/tests/test_projector.py`

**Interfaces:**
- Consumes: `TypeSnapshot`, `GraphUnavailable`, `OntoObject`, `OntoRelation`, `InstanceSuggestionDraft`, `InstanceRelDraft`
- Produces:

```python
@dataclass
class GraphNode:
    onto_iri: str
    type_iri: str
    onto_label: str
    evidence: str
    block_id: str
    data: dict
    native_label: str = "OntoNode"

@dataclass
class GraphRel:
    rel_id: str
    source_iri: str
    target_iri: str
    predicate_iri: str
    onto_label: str
    evidence: str
    block_id: str

@dataclass
class InstanceNetwork:
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphRel, ...]

class GraphRepository(Protocol):
    def upsert_node(self, node: GraphNode) -> None: ...
    def upsert_rel(self, rel: GraphRel) -> None: ...
    def get_node(self, onto_iri: str) -> GraphNode | None: ...
    def delete_node(self, onto_iri: str) -> None: ...
    def delete_rel(self, rel_id: str) -> None: ...
    def instance_network(self, type_iri: str | None = None) -> InstanceNetwork: ...
    def update_type_display(self, type_iri: str, onto_label: str) -> int: ...
    def count_nodes_of_type(self, type_iri: str) -> int: ...
    def count_rels_of_predicate(self, predicate_iri: str) -> int: ...
    def count_nodes_with_attribute(self, attr_iri: str) -> int: ...

class MemoryGraphRepository:
    ...

class Projector:
    def __init__(self, graph: GraphRepository) -> None: ...
    def register_type(self, type_iri: str, display_label: str) -> None: ...
    def display_label(self, type_iri: str) -> str: ...
    def project_instances(
        self,
        snapshot: TypeSnapshot,
        instances: list[InstanceSuggestionDraft],
        rels: list[InstanceRelDraft],
        *,
        iri_prefix: str,
    ) -> tuple[list[str], list[str]]:
        """返回 (projected_iris, skipped_reasons)。type_iri 不在 snapshot.objects 则 skip。"""
    def sync_object_label(self, type_iri: str, label: str) -> None: ...
```

`update_type_display` 只改匹配 `type_iri` 的节点的 `onto_label`，**不得**改 `native_label`。实例 IRI = `iri_prefix + local_id`。关系 `rel_id` 用 UUID。投影时关系的 `predicate_iri` 必须在 `snapshot.relations` 中，且两端实例已投影。

- [ ] **Step 1: Write the failing test**

```python
from ontocore.constants import NS
from ontocore.graph.memory import MemoryGraphRepository
from ontocore.graph.projector import Projector
from ontocore.models import InstanceSuggestionDraft, OntoObject, TypeSnapshot


def test_skip_unconfirmed_object():
    g = MemoryGraphRepository()
    p = Projector(g)
    snap = TypeSnapshot(
        objects=(OntoObject(iri=f"{NS}Product", label="产品", definition="d"),),
        attributes=(),
        relations=(),
    )
    inst = [InstanceSuggestionDraft(
        local_id="e1", type_iri=f"{NS}Unknown", label="x", data={}, evidence="e", block_id="b", confidence=1.0,
    )]
    ok, skipped = p.project_instances(snap, inst, [], iri_prefix=NS)
    assert ok == []
    assert skipped


def test_project_and_rename_keeps_iri():
    g = MemoryGraphRepository()
    p = Projector(g)
    iri = f"{NS}Product"
    snap = TypeSnapshot(objects=(OntoObject(iri=iri, label="产品", definition="d"),), attributes=(), relations=())
    p.register_type(iri, "产品")
    inst = [InstanceSuggestionDraft(
        local_id="p1", type_iri=iri, label="尊享", data={}, evidence="e", block_id="b", confidence=1.0,
    )]
    ok, skipped = p.project_instances(snap, inst, [], iri_prefix=NS)
    assert skipped == []
    node_iri = ok[0]
    p.sync_object_label(iri, "保险产品")
    node = g.get_node(node_iri)
    assert node is not None
    assert node.onto_iri == node_iri
    assert node.onto_label == "保险产品"
    assert node.native_label == "OntoNode"


def test_delete_instance():
    g = MemoryGraphRepository()
    p = Projector(g)
    iri = f"{NS}Product"
    snap = TypeSnapshot(objects=(OntoObject(iri=iri, label="产品", definition="d"),), attributes=(), relations=())
    inst = [InstanceSuggestionDraft(
        local_id="p1", type_iri=iri, label="尊享", data={}, evidence="e", block_id="b", confidence=1.0,
    )]
    ok, _ = p.project_instances(snap, inst, [], iri_prefix=NS)
    g.delete_node(ok[0])
    assert g.get_node(ok[0]) is None
    assert g.instance_network().nodes == ()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend; python -m pytest tests/test_projector.py -v`

Expected: FAIL cannot import `Projector`

- [ ] **Step 3: Write minimal implementation**

`MemoryGraphRepository` 用 dict。`Projector.project_instances`：对象 IRI 集合来自 `snapshot.objects`；不在集合则 `skipped_reasons` 追加中文原因「对象未确认：{type_iri}」；在则 `upsert_node`。`sync_object_label` 调 `register_type` + `update_type_display`。

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend; python -m pytest tests/test_projector.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/ontocore/graph backend/tests/test_projector.py
git commit -m "feat: add in-memory graph projector and instance delete"
```

---

### Task 5: Neo4j GraphRepository 适配器

**Files:**
- Create: `backend/src/ontocore/graph/neo4j_repo.py`
- Test: `backend/tests/test_neo4j_repo.py`

**Interfaces:**
- Consumes: `GraphRepository`, `GraphNode`, `GraphRel`, `GraphUnavailable`
- Produces: `Neo4jGraphRepository` 实现 Task 4 的 Protocol

节点 `(:OntoNode {onto_iri, type_iri, onto_label, evidence, block_id, data_json})`。边 `[:ONTO_REL {rel_id, predicate_iri, onto_label, evidence, block_id}]`。`update_type_display`：`MATCH (n:OntoNode {type_iri:$t}) SET n.onto_label=$l`，不 `REMOVE`/`SET` 原生 label。连接失败抛 `GraphUnavailable`。

- [ ] **Step 1: Write the failing test**

```python
from ontocore.graph.neo4j_repo import Neo4jGraphRepository
from ontocore.errors import GraphUnavailable


def test_unavailable_on_bad_uri():
    repo = Neo4jGraphRepository("bolt://127.0.0.1:1", "neo4j", "test")
    try:
        repo.instance_network()
    except GraphUnavailable:
        return
    raise AssertionError("expected GraphUnavailable")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend; python -m pytest tests/test_neo4j_repo.py -v`

Expected: FAIL cannot import `Neo4jGraphRepository`

- [ ] **Step 3: Write minimal implementation**

构造时保存 uri/user/password，每次操作开 `GraphDatabase.driver`。捕获连接/认证错误为 `GraphUnavailable`。`data` 存 JSON 字符串。

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend; python -m pytest tests/test_neo4j_repo.py -v`

Expected: PASS（不要求本机 Neo4j 在跑）

- [ ] **Step 5: Commit**

```bash
git add backend/src/ontocore/graph/neo4j_repo.py backend/tests/test_neo4j_repo.py
git commit -m "feat: add Neo4j graph repository adapter"
```

---

### Task 6: DocumentIngress

**Files:**
- Create: `backend/src/ontocore/extract/__init__.py`
- Create: `backend/src/ontocore/extract/ingress.py`
- Test: `backend/tests/test_ingress.py`

**Interfaces:**
- Consumes: `IngressError`, `ParsedDocument`, `TextBlock`
- Produces: `parse_upload(filename: str, data: bytes) -> ParsedDocument`

`.txt`：按空行切 `paragraph`，以 `#` 或全行短标题（长度 < 40 且无句号）为 `heading`。`.pdf` 用 pypdf；加密或无文本 → `IngressError`。`.docx` 用 python-docx。其它后缀 → `IngressError`。`block_id` 为 `b0`、`b1`…

- [ ] **Step 1: Write the failing test**

```python
from ontocore.extract.ingress import parse_upload
from ontocore.errors import IngressError


def test_plain_text_blocks():
    doc = parse_upload("a.txt", "标题\n\n第一段。".encode("utf-8"))
    assert doc.filename == "a.txt"
    assert "第一段" in doc.full_text
    assert doc.blocks


def test_unknown_suffix():
    try:
        parse_upload("a.bin", b"x")
    except IngressError:
        return
    raise AssertionError("expected IngressError")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend; python -m pytest tests/test_ingress.py -v`

Expected: FAIL cannot import `parse_upload`

- [ ] **Step 3: Write minimal implementation**

按上面规则实现。空字节 → `IngressError("无法提取文本")`。

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend; python -m pytest tests/test_ingress.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/ontocore/extract/ingress.py backend/src/ontocore/extract/__init__.py backend/tests/test_ingress.py
git commit -m "feat: add document ingress for txt pdf docx"
```

---

### Task 7: LlmGateway

**Files:**
- Create: `backend/src/ontocore/extract/llm.py`
- Test: `backend/tests/test_llm_gateway.py`

**Interfaces:**
- Consumes: `StructuredOutputError`
- Produces:

```python
class LlmGateway(Protocol):
    def complete_structured(self, schema: dict, messages: list[dict]) -> dict: ...

class LiteLlmGateway:
    def __init__(self, model: str) -> None: ...
    def complete_structured(self, schema: dict, messages: list[dict]) -> dict: ...

class FakeLlmGateway:
    def __init__(self, canned: dict) -> None: ...
    def complete_structured(self, schema: dict, messages: list[dict]) -> dict: ...
```

`LiteLlmGateway` 调用 `litellm.completion`（`response_format` 用 json schema 或要求 JSON 文本再 `json.loads`）。解析失败抛 `StructuredOutputError`。`FakeLlmGateway` 忽略 messages，原样返回 `canned`（测试用）。

- [ ] **Step 1: Write the failing test**

```python
from ontocore.extract.llm import FakeLlmGateway


def test_fake_returns_canned():
    gw = FakeLlmGateway({"objects": []})
    assert gw.complete_structured({}, []) == {"objects": []}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend; python -m pytest tests/test_llm_gateway.py -v`

Expected: FAIL cannot import `FakeLlmGateway`

- [ ] **Step 3: Write minimal implementation**

实现 `FakeLlmGateway` 与 `LiteLlmGateway`。后者 `import litellm` 仅在方法内。

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend; python -m pytest tests/test_llm_gateway.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/ontocore/extract/llm.py backend/tests/test_llm_gateway.py
git commit -m "feat: add LLM gateway with fake and LiteLLM adapters"
```

---

### Task 8: 抽取器（无领域包）

**Files:**
- Create: `backend/src/ontocore/extract/ports.py`
- Create: `backend/src/ontocore/extract/llm_only.py`
- Create: `backend/src/ontocore/extract/hybrid.py`
- Create: `backend/src/ontocore/extract/rules_only.py`
- Create: `backend/src/ontocore/extract/registry.py`
- Test: `backend/tests/test_extractors.py`

**Interfaces:**
- Consumes: `ParsedDocument`, `TypeSnapshot`, `LlmGateway`, `ExtractionResult`, `NS`
- Produces:

```python
class Extractor(Protocol):
    name: str
    def extract(self, doc: ParsedDocument, snapshot: TypeSnapshot, llm: LlmGateway) -> ExtractionResult: ...

def get_extractor(name: str) -> Extractor: ...
```

`inspect.signature(Extractor.extract)` 不得含 `domain` 参数。`get_extractor` 仅注册 `hybrid`、`llm_only`、`rules_only`。仓库内不得存在 `DomainPack` 类型。

`llm_only`：把 `snapshot` 序列化成「已有对象/属性/关系」列表放入 prompt；`complete_structured` 的 schema 含 `object_candidates`、`attribute_candidates`、`relation_candidates`、`instance_suggestions`、`instance_rel_suggestions`；把返回 dict 填进 `ExtractionResult`。缺字段当空列表。

`hybrid`：按 heading 切块；块标题若等于某对象 `label` 则该块 `type_iri` 对齐该对象；再对每块调用 llm（可一次全文档）。

`rules_only`：不调 llm。对每个 heading 块：若标题等于已有对象 label，产出 `InstanceSuggestionDraft(local_id=block_id, type_iri=该对象, label=块首行, ...)`；否则产出 `ObjectCandidateDraft`（本地名由标题字母数字化，非法则 `obj_{block_id}`）。

- [ ] **Step 1: Write the failing test**

```python
import inspect
from ontocore.constants import NS
from ontocore.extract.llm import FakeLlmGateway
from ontocore.extract.registry import get_extractor
from ontocore.models import OntoObject, ParsedDocument, TextBlock, TypeSnapshot


def test_extract_signature_has_no_domain_pack():
    sig = inspect.signature(get_extractor("hybrid").extract)
    assert "domain" not in sig.parameters
    assert "domain_pack" not in sig.parameters


def test_llm_only_with_fake():
    canned = {
        "object_candidates": [],
        "attribute_candidates": [],
        "relation_candidates": [],
        "instance_suggestions": [{
            "local_id": "i1", "type_iri": f"{NS}Product", "label": "尊享",
            "data": {}, "evidence": "尊享医疗保险", "block_id": "b0", "confidence": 0.8,
        }],
        "instance_rel_suggestions": [],
    }
    doc = ParsedDocument("a.txt", "尊享医疗保险", (TextBlock("b0", "paragraph", "尊享医疗保险"),))
    snap = TypeSnapshot(objects=(OntoObject(iri=f"{NS}Product", label="保险产品", definition="d"),), attributes=(), relations=())
    result = get_extractor("llm_only").extract(doc, snap, FakeLlmGateway(canned))
    assert result.instance_suggestions[0].label == "尊享"


def test_rules_only_proposes_new_object_when_unaligned():
    doc = ParsedDocument("a.txt", "等待期\n\n30天。", (
        TextBlock("b0", "heading", "等待期"),
        TextBlock("b1", "paragraph", "30天。"),
    ))
    snap = TypeSnapshot(objects=(), attributes=(), relations=())
    result = get_extractor("rules_only").extract(doc, snap, FakeLlmGateway({}))
    assert result.object_candidates
    assert result.object_candidates[0].label == "等待期"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend; python -m pytest tests/test_extractors.py -v`

Expected: FAIL cannot import `get_extractor`

- [ ] **Step 3: Write minimal implementation**

实现三抽取器与 registry。`llm_only` 对 canned 用 `**(item)` 构造 dataclass（只取已知字段）。

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend; python -m pytest tests/test_extractors.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/ontocore/extract backend/tests/test_extractors.py
git commit -m "feat: add extractors aligned to current ontology snapshot"
```

---

### Task 9: Job 服务、类型审阅、一键投影

**Files:**
- Create: `backend/src/ontocore/jobs/__init__.py`
- Create: `backend/src/ontocore/jobs/store.py`
- Create: `backend/src/ontocore/jobs/service.py`
- Create: `backend/src/ontocore/review/__init__.py`
- Create: `backend/src/ontocore/review/service.py`
- Test: `backend/tests/test_review_and_jobs.py`

**Interfaces:**
- Consumes: 前述全部仓库、抽取器、`CandidateStore`、`Projector`
- Produces:

```python
@dataclass
class Job:
    id: str
    filename: str
    extractor: str
    model: str
    status: JobStatus
    error: str | None

class JobStore:
    def __init__(self, sqlite_path: str) -> None: ...
    def create(self, filename: str, extractor: str, model: str) -> Job: ...
    def get(self, job_id: str) -> Job: ...
    def set_status(self, job_id: str, status: JobStatus, error: str | None = None) -> Job: ...

class JobService:
    def __init__(self, jobs: JobStore, candidates: CandidateStore, ontology: OntologyRepository, llm_factory) -> None: ...
    def run(self, job_id: str, filename: str, data: bytes) -> Job: ...

class ReviewService:
    def accept_type(self, candidate_id: str) -> StoredTypeCandidate: ...
    def reject_type(self, candidate_id: str) -> StoredTypeCandidate: ...
    def project_job(self, job_id: str) -> dict: ...  # {projected: list[str], skipped: list[str]}
```

`JobService.run`：`running` → `parse_upload` → `get_extractor` → `ontology.snapshot()` → `extract` → `replace_job_results`。有 `block_failures` 且有候选 → `partial`；解析失败 → `failed`；成功无失败块 → `completed`。`llm_factory(model) -> LlmGateway`。作业记录不含领域包字段。

`accept_type`：按 `kind` 调用 `create_object` / `create_attribute` / `create_relation`（payload 字段对应模型），再 `set_type_status(..., "accepted")`，并 `projector.register_type`。`reject_type` 只改状态。没有 `accept_instance`。

`project_job`：读该 job 实例候选 status=`proposed`；`projector.project_instances`；成功的 `set_instance_status(..., "projected")`，跳过的 `"skipped"`。`GraphUnavailable` → 作业 `types_accepted_graph_pending`，已接受类型不回滚。

删除对象前服务层：`graph.count_nodes_of_type(iri)>0` → `ConflictError("仍有实例占用该对象")`。删属性：`count_nodes_with_attribute`。删关系：`count_rels_of_predicate`。

- [ ] **Step 1: Write the failing test**

```python
from ontocore.candidates.store import CandidateStore
from ontocore.constants import NS
from ontocore.extract.llm import FakeLlmGateway
from ontocore.graph.memory import MemoryGraphRepository
from ontocore.graph.projector import Projector
from ontocore.jobs.service import JobService
from ontocore.jobs.store import JobStore
from ontocore.ontology.repository import OntologyRepository
from ontocore.review.service import ReviewService


def test_accept_object_then_project(tmp_path):
    sqlite = str(tmp_path / "j.db")
    ontology = OntologyRepository()
    graph = MemoryGraphRepository()
    projector = Projector(graph)
    candidates = CandidateStore(sqlite)
    jobs = JobStore(sqlite)
    def llm_factory(model):
        return FakeLlmGateway({
            "object_candidates": [{
                "iri": f"{NS}Product", "label": "保险产品", "definition": "d",
                "parent_iri": None, "evidence": "产品", "block_id": "b0", "confidence": 1.0,
            }],
            "attribute_candidates": [],
            "relation_candidates": [],
            "instance_suggestions": [{
                "local_id": "p1", "type_iri": f"{NS}Product", "label": "尊享",
                "data": {}, "evidence": "尊享", "block_id": "b0", "confidence": 1.0,
            }],
            "instance_rel_suggestions": [],
        })
    js = JobService(jobs, candidates, ontology, llm_factory)
    job = jobs.create("a.txt", "llm_only", "fake")
    js.run(job.id, "a.txt", "尊享医疗保险".encode("utf-8"))
    review = ReviewService(candidates, ontology, projector, jobs, graph)
    types = candidates.list_type_candidates(job.id)
    review.accept_type(types[0].id)
    assert any(o.label == "保险产品" for o in ontology.snapshot().objects)
    out = review.project_job(job.id)
    assert out["projected"]
    assert graph.instance_network().nodes
    assert not hasattr(review, "accept_instance")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend; python -m pytest tests/test_review_and_jobs.py -v`

Expected: FAIL cannot import `ReviewService`

- [ ] **Step 3: Write minimal implementation**

按接口实现。`JobStore` 表 `jobs(id, filename, extractor, model, status, error)`。`ReviewService.__init__(self, candidates, ontology, projector, jobs, graph)`。

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend; python -m pytest tests/test_review_and_jobs.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/ontocore/jobs backend/src/ontocore/review backend/tests/test_review_and_jobs.py
git commit -m "feat: add jobs, type review, and one-click instance projection"
```

---

### Task 10: FastAPI（产品语言，无领域包）

**Files:**
- Create: `backend/src/ontocore/settings.py`
- Create: `backend/src/ontocore/api/__init__.py`
- Create: `backend/src/ontocore/api/app.py`
- Test: `backend/tests/test_api.py`

**Interfaces:**
- Consumes: Task 1–9
- Produces: `create_app() -> FastAPI`

`create_app` **不得** import 种子、不得 `import_turtle`。设置 `extractor` 默认 `hybrid`，`model` 默认 `openai/gpt-4o-mini`。图：无 `NEO4J_URI` 用内存图。

路由（JSON 字段用 `object`/`attribute`/`relation`/`definition`，错误正文用中文「对象」等）：

- `GET /api/objects` `POST /api/objects` `PATCH /api/objects/{local_name}` `DELETE /api/objects/{local_name}`
- `POST /api/objects/{local_name}/attributes` `PATCH /api/attributes/{local_name}` `DELETE /api/attributes/{local_name}`
- `GET /api/relations` `POST /api/relations` `PATCH /api/relations/{local_name}` `DELETE /api/relations/{local_name}`
- `GET /api/ontology/network` → `TypeNetwork`
- `GET /api/ontology/export?format=turtle|jsonld` `POST /api/ontology/import`（query `force`）
- `POST /api/jobs` multipart file + extractor + model；`GET /api/jobs/{id}`
- `GET /api/jobs/{id}/type-candidates`；`POST /api/type-candidates/{id}/accept`；`POST /api/type-candidates/{id}/reject`
- `POST /api/jobs/{id}/project`
- `GET /api/graph/network?type_iri=`；`DELETE /api/graph/nodes/{iri}`；`DELETE /api/graph/rels/{rel_id}`
- `GET /api/settings` `PUT /api/settings`（仅 extractor、model）

`OntologyWriteError` → 400；`ConflictError` → 409；`IngressError` → 400；`GraphUnavailable` → 503，正文说明图不可用。响应与 OpenAPI 描述禁止出现「领域包」「TBox」「类」。`DELETE` 对象前走 `ReviewService`/`app` 内引用检查。

- [ ] **Step 1: Write the failing test**

```python
from fastapi.testclient import TestClient
from ontocore.api.app import create_app


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend; python -m pytest tests/test_api.py -v`

Expected: FAIL cannot import `create_app`

- [ ] **Step 3: Write minimal implementation**

Pydantic 请求体：`local_name`、`label`、`definition`、`parent_local_name`、`literal_kind`、`source_local_name`、`target_local_name`。IRI = `NS + local_name`。

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend; python -m pytest tests/test_api.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/ontocore/api backend/src/ontocore/settings.py backend/tests/test_api.py
git commit -m "feat: add HTTP API for objects, relations, jobs, and projection"
```

---

### Task 11: 前端五页（类型网 + 实例网）

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`（`server.proxy."/api"` → `http://127.0.0.1:8001`）
- Create: `frontend/tsconfig.json`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/api.ts`
- Create: `frontend/src/pages/OntologyPage.tsx`
- Create: `frontend/src/pages/UploadPage.tsx`
- Create: `frontend/src/pages/ReviewPage.tsx`
- Create: `frontend/src/pages/GraphPage.tsx`
- Create: `frontend/src/pages/SettingsPage.tsx`
- Create: `frontend/src/components/TypeNetwork.tsx`
- Create: `frontend/src/components/InstanceNetwork.tsx`
- Test: `frontend/src/api.test.ts`

**Interfaces:**
- Consumes: Task 10 JSON
- Produces: 可运行 Vite 应用

页签文案：**本体、上传、审阅、图、设置**。禁止字符串：`TBox`、`领域包`、`类`、`对象属性`、`数据属性`。

`TypeNetwork` / `InstanceNetwork`：用 SVG，节点为圆+label，边为带箭头直线（可按节点数字索引均匀摆圆上）。点击节点/边调用传入的 `onSelect`。空节点时显示「还没有对象，请先新建」或「还没有实例」。

本体页：左列对象列表与新建表单（显示名、定义、父对象下拉、本地名）；选中后属性表；关系表（起点/终点各选一个对象）。主区类型网。

上传页：file input、抽取器 select（hybrid/llm_only/rules_only）、模型 input、作业状态。无领域包控件。

审阅页：只列出 type-candidates；接受/拒绝；按钮「投影到图」调 `POST /api/jobs/{id}/project`。不渲染实例接受按钮。

图页：实例网、按 type_iri 筛选、删除节点按钮。

设置页：extractor、model、导出链接、导入 textarea + force checkbox。

- [ ] **Step 1: Write the failing test**

`frontend/src/api.test.ts`：用 node 内置 `node:test` 或 vitest。断言 `frontend/src/App.tsx` 与页面源码不含 `领域包`、`TBox`、`acceptInstance`。

```ts
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";
import assert from "node:assert/strict";

describe("copy", () => {
  it("does not mention domain pack or TBox", () => {
    const files = [
      "src/App.tsx",
      "src/pages/OntologyPage.tsx",
      "src/pages/ReviewPage.tsx",
      "src/pages/UploadPage.tsx",
    ];
    for (const f of files) {
      const t = readFileSync(f, "utf8");
      assert.equal(t.includes("领域包"), false, f);
      assert.equal(t.includes("TBox"), false, f);
    }
  });
});
```

若 Vite 项目用 vitest，把测试写成 vitest 并在 `package.json` 加 `"test": "vitest run"`。

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend; npm test`

Expected: FAIL missing files

- [ ] **Step 3: Write minimal implementation**

`package.json` dependencies: `react`, `react-dom`, `react-router-dom`。dev: `vite`, `typescript`, `@types/react`, `vitest`。`api.ts` 封装 fetch。后端端口 8001（避免 8000 占用）。

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend; npm install; npm test`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend
git commit -m "feat: add web UI with type and instance networks"
```

---

### Task 12: Fixture 回归、docker-compose、README

**Files:**
- Create: `backend/tests/fixtures/sample.txt`
- Create: `backend/tests/test_fixture_regression.py`
- Create: `docker-compose.yml`
- Modify: `README.md`

**Interfaces:**
- Consumes: 全应用
- Produces: 回归测试与运行说明

`sample.txt` 脱敏说明书片段，含标题「保险责任」与一段产品名。回归：空库 `type_network` 为空；`rules_only` 对空快照产出对象候选；对已有「保险产品」对象的快照可产出实例建议；`create_app` 路由无 `domain`。

`docker-compose.yml` 仅 Neo4j 可选。README 写：实现以对象关系规格为准；如何 `pip install`、`uvicorn ontocore.api.app:create_app --factory --port 8001`、`npm run dev`；空库无种子；无领域包。

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path
from ontocore.api.app import create_app
from ontocore.extract.ingress import parse_upload
from ontocore.extract.llm import FakeLlmGateway
from ontocore.extract.registry import get_extractor
from ontocore.models import TypeSnapshot


def test_empty_app_and_fixture_extract():
    app = create_app()
    assert not any("domain" in getattr(r, "path", "") for r in app.routes)
    text = Path(__file__).parent.joinpath("fixtures/sample.txt").read_bytes()
    doc = parse_upload("sample.txt", text)
    result = get_extractor("rules_only").extract(doc, TypeSnapshot(objects=(), attributes=(), relations=()), FakeLlmGateway({}))
    assert result.object_candidates or result.instance_suggestions
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend; python -m pytest tests/test_fixture_regression.py -v`

Expected: FAIL missing fixture or assertion

- [ ] **Step 3: Write fixture, compose, README**

`sample.txt` 至少 8 行中文，含「保险责任」标题。Compose：

```yaml
services:
  neo4j:
    image: neo4j:5
    ports: ["7474:7474", "7687:7687"]
    environment:
      NEO4J_AUTH: neo4j/testtesttest
```

- [ ] **Step 4: Run all backend tests**

Run: `cd backend; python -m pytest -v`

Expected: PASS all

- [ ] **Step 5: Commit**

```bash
git add backend/tests/fixtures backend/tests/test_fixture_regression.py docker-compose.yml README.md
git commit -m "docs: add runbook and fixture regression without domain packs"
```

---

## Self-review notes (author)

- Spec §1–11 均有对应任务：CRUD/网=T2+T10+T11；抽取=T6–T8；只审类型+投影=T3+T9；图删除=T4；导入导出=T2+T10；空库/无领域包=T2/T8/T10/T12；显示名同步=T4。
- 无 TBD；类型名在后续任务与 Task 1 `models.py` 一致。
- 旧计划中的 `insurance-product`、`DomainPack`、`OwlClass`、`tbox_accepted_graph_pending`、`accept instance` 均不采用。
