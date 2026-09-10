# OntoCore 第一期 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建成可演示的 OntoCore：上传中文保险产品说明书，可插拔抽取候选 TBox/ABox，人审后写入 OWL（Oxigraph）与实例图（Neo4j/内存适配器），支持手工建类、OWL 导入导出，以及按 IRI + `onto_label` 的显示名同步。

**Architecture:** Python 模块化单体（FastAPI）+ TypeScript Web。核心只依赖 Protocol；Oxigraph、Neo4j、LiteLLM、抽取器、领域包均为适配器。权威 TBox 与图投影分步提交，不用分布式事务。

**Tech Stack:** Python 3.12、FastAPI、pyoxigraph、SQLite、neo4j 驱动、LiteLLM、pypdf、python-docx、pytest；前端 Vite + React + TypeScript。

## Global Constraints

- 工作本体 id 固定为 `insurance-product`；IRI 前缀 `https://ontocore.local/ns/insurance-product#`。
- TBox 权威存 RDF/OWL 小剖面；ABox 只进图；图不可用时不得把实例写入 OWL。
- OWL 只允许：类、`rdfs:subClassOf`、对象/数据属性、`rdfs:domain`/`rdfs:range`、可选两个命名类的 `owl:disjointWith`。禁止复杂匿名类与全量 OWL 2 DL。
- 导出/导入格式：Turtle 与 JSON-LD；导入同 IRI 默认拒绝覆盖，除非 `force=true`。
- 抽取器不得写 TBox 或图；候选状态仅 `proposed` / `accepted` / `rejected`。
- LLM 只经 `complete_structured`；底层 LiteLLM；抽取器内禁止直连厂商 SDK。
- 默认识别器 `hybrid`；内置 `llm_only`；预留并实现最小 `rules_only`（仅标题规则、无 LLM）。
- 图同步：节点/边写 `onto_iri`、`onto_label`；原生 Neo4j label 固定为 `OntoNode` / `ONTO_REL`，同步不改原生 label。
- 未在领域包声明且未接受的类型不得投影到权威图。
- 第一期不做 OCR、准确率 CI 门槛、多租户、完整公理编辑器。
- 作业状态包含：`queued`、`running`、`failed`、`partial`、`completed`、`tbox_accepted_graph_pending`。

---

## File structure

```
backend/pyproject.toml
backend/src/ontocore/__init__.py
backend/src/ontocore/constants.py          # ONTOLOGY_ID, NS
backend/src/ontocore/errors.py
backend/src/ontocore/models.py             # 全部 dataclass
backend/src/ontocore/tbox/profile.py       # 剖面校验
backend/src/ontocore/tbox/repository.py    # Oxigraph TBoxRepository
backend/src/ontocore/candidates/store.py
backend/src/ontocore/graph/ports.py        # GraphRepository Protocol
backend/src/ontocore/graph/memory.py
backend/src/ontocore/graph/neo4j_repo.py
backend/src/ontocore/graph/projector.py
backend/src/ontocore/extract/ingress.py
backend/src/ontocore/extract/llm.py
backend/src/ontocore/extract/ports.py      # Extractor, DomainPack, LlmGateway
backend/src/ontocore/extract/llm_only.py
backend/src/ontocore/extract/hybrid.py
backend/src/ontocore/extract/rules_only.py
backend/src/ontocore/extract/registry.py
backend/src/ontocore/domain/insurance_product/pack.py
backend/src/ontocore/domain/insurance_product/seed.ttl
backend/src/ontocore/domain/insurance_product/fixture_excerpt.txt
backend/src/ontocore/jobs/store.py
backend/src/ontocore/jobs/service.py
backend/src/ontocore/review/service.py     # accept/reject + 投影
backend/src/ontocore/settings.py
backend/src/ontocore/api/app.py
backend/tests/...
frontend/package.json
frontend/src/App.tsx
frontend/src/api.ts
frontend/src/pages/*.tsx
docker-compose.yml                     # Neo4j 可选
```

---

### Task 1: 常量、错误类型、共享模型、OWL 剖面校验

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/src/ontocore/__init__.py`
- Create: `backend/src/ontocore/constants.py`
- Create: `backend/src/ontocore/errors.py`
- Create: `backend/src/ontocore/models.py`
- Create: `backend/src/ontocore/tbox/__init__.py`
- Create: `backend/src/ontocore/tbox/profile.py`
- Test: `backend/tests/test_profile.py`

**Interfaces:**
- Consumes: 无
- Produces: `ONTOLOGY_ID`, `NS`, `TBoxWriteError`, `OwlClass`, `OwlProperty`, `TBoxSnapshot`, `assert_profile_turtle(ttl: str) -> None`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_profile.py
from ontocore.constants import NS
from ontocore.errors import ProfileViolation
from ontocore.tbox.profile import assert_profile_turtle


def test_named_class_hierarchy_ok():
    ttl = f"""
    @prefix : <{NS}> .
    @prefix owl: <http://www.w3.org/2002/07/owl#> .
    @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
    :Product a owl:Class ; rdfs:label "保险产品" .
    :Coverage a owl:Class ; rdfs:subClassOf :Product ; rdfs:label "责任" .
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

Run: `cd backend && python -m pytest tests/test_profile.py -v`

Expected: FAIL with `ModuleNotFoundError` or `cannot import ontocore`

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

`constants.py`：`ONTOLOGY_ID = "insurance-product"`，`NS = "https://ontocore.local/ns/insurance-product#"`。

`errors.py`：`ProfileViolation`、`TBoxWriteError`、`IngressError`、`GraphUnavailable`、`StructuredOutputError`。

`models.py` 定义（后续任务必须原样使用这些名字）：

```python
from dataclasses import dataclass, field
from typing import Any, Literal

CandidateStatus = Literal["proposed", "accepted", "rejected"]
PropertyKind = Literal["object", "data"]
JobStatus = Literal[
    "queued", "running", "failed", "partial", "completed",
    "tbox_accepted_graph_pending",
]

@dataclass(frozen=True)
class OwlClass:
    iri: str
    label: str
    parent_iri: str | None = None

@dataclass(frozen=True)
class OwlProperty:
    iri: str
    label: str
    kind: PropertyKind
    domain_iri: str | None = None
    range_iri: str | None = None

@dataclass(frozen=True)
class TBoxSnapshot:
    classes: tuple[OwlClass, ...]
    properties: tuple[OwlProperty, ...]

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
class ClassCandidateDraft:
    iri: str
    label: str
    parent_iri: str | None
    evidence: str
    block_id: str
    confidence: float

@dataclass
class PropertyCandidateDraft:
    iri: str
    label: str
    kind: PropertyKind
    domain_iri: str | None
    range_iri: str | None
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
class RelationSuggestionDraft:
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
    class_candidates: list[ClassCandidateDraft]
    property_candidates: list[PropertyCandidateDraft]
    instance_suggestions: list[InstanceSuggestionDraft]
    relation_suggestions: list[RelationSuggestionDraft]
    block_failures: list[BlockFailure] = field(default_factory=list)
```

`profile.py`：用 `pyoxigraph.Store` 解析 Turtle；若存在 `owl:Restriction` 或空白节点作为 `rdfs:subClassOf` 对象，抛 `ProfileViolation`。允许 `owl:Class`、`owl:ObjectProperty`、`owl:DatatypeProperty`、`rdfs:subClassOf` 指向 IRI、`rdfs:domain`/`range`、`owl:disjointWith` 两端均为 IRI。

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pip install -e ".[dev]" && python -m pytest tests/test_profile.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/pyproject.toml backend/src/ontocore backend/tests/test_profile.py
git commit -m "feat: add OWL profile validator and shared models"
```

---

### Task 2: TBoxRepository（Oxigraph）手工写入与导入导出

**Files:**
- Create: `backend/src/ontocore/tbox/repository.py`
- Test: `backend/tests/test_tbox_repository.py`

**Interfaces:**
- Consumes: `OwlClass`, `OwlProperty`, `TBoxSnapshot`, `assert_profile_turtle`, `TBoxWriteError`, `NS`
- Produces:

```python
class TBoxRepository:
    def __init__(self, path: str | None = None) -> None: ...
    def snapshot(self) -> TBoxSnapshot: ...
    def create_class(self, item: OwlClass) -> None: ...
    def create_property(self, item: OwlProperty) -> None: ...
    def update_label(self, iri: str, label: str) -> None: ...
    def migrate_iri(self, old_iri: str, new_iri: str) -> None: ...
    def export_turtle(self) -> str: ...
    def export_jsonld(self) -> str: ...
    def import_turtle(self, ttl: str, *, force: bool = False) -> None: ...
    def has_iri(self, iri: str) -> bool: ...
```

同一时刻仅一个写事务：实例内 `threading.RLock()`。`create_class`：父类非空且不存在 → `TBoxWriteError`；IRI 已存在 → `TBoxWriteError`。`create_property`：domain/range 若设则必须已是类。`import_turtle`：先 `assert_profile_turtle`；无 force 时若导入图中 IRI 与库中已有命名类/属性 IRI 交集非空 → `TBoxWriteError`；force 时用导入文件替换冲突三元组（删除旧 iri 的类型与 label 断言后加载）。`export_jsonld` 可用 rdflib 或手写最小 JSON-LD（`@context` + `@graph`）；为少依赖，用 pyoxigraph serialize `application/ld+json`（若版本不支持则 Turtle 转简单 `@graph` 列表，测试只断言包含类 IRI 字符串）。

- [ ] **Step 1: Write the failing test**

```python
from ontocore.constants import NS
from ontocore.errors import TBoxWriteError
from ontocore.models import OwlClass, OwlProperty
from ontocore.tbox.repository import TBoxRepository

def test_create_and_snapshot():
    repo = TBoxRepository()
    repo.create_class(OwlClass(iri=f"{NS}Product", label="保险产品"))
    snap = repo.snapshot()
    assert any(c.iri.endswith("Product") and c.label == "保险产品" for c in snap.classes)

def test_missing_parent_rejected():
    repo = TBoxRepository()
    try:
        repo.create_class(OwlClass(iri=f"{NS}A", label="A", parent_iri=f"{NS}Missing"))
    except TBoxWriteError:
        return
    raise AssertionError("expected TBoxWriteError")

def test_import_same_iri_rejected_without_force():
    repo = TBoxRepository()
    repo.create_class(OwlClass(iri=f"{NS}Product", label="保险产品"))
    ttl = repo.export_turtle()
    try:
        repo.import_turtle(ttl, force=False)
    except TBoxWriteError:
        return
    raise AssertionError("expected TBoxWriteError")

def test_import_force_overwrites_label():
    repo = TBoxRepository()
    repo.create_class(OwlClass(iri=f"{NS}Product", label="旧"))
    ttl = f'@prefix : <{NS}> . @prefix owl: <http://www.w3.org/2002/07/owl#> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . :Product a owl:Class ; rdfs:label "新" .'
    repo.import_turtle(ttl, force=True)
    labels = {c.iri: c.label for c in repo.snapshot().classes}
    assert labels[f"{NS}Product"] == "新"

def test_property_unknown_domain_rejected():
    repo = TBoxRepository()
    try:
        repo.create_property(OwlProperty(iri=f"{NS}hasCoverage", label="含", kind="object", domain_iri=f"{NS}Product", range_iri=f"{NS}Coverage"))
    except TBoxWriteError:
        return
    raise AssertionError("expected TBoxWriteError")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_tbox_repository.py -v`

Expected: FAIL import error `TBoxRepository`

- [ ] **Step 3: Write minimal implementation**

Oxigraph `Store` 内存或 `path` 目录。前缀绑定 `:` → `NS`。`snapshot` 查询所有 `owl:Class` / 属性及 `rdfs:label`、`rdfs:subClassOf`（仅 IRI 父类）。

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_tbox_repository.py tests/test_profile.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/ontocore/tbox/repository.py backend/tests/test_tbox_repository.py
git commit -m "feat: add Oxigraph TBox repository with import force flag"
```

---

### Task 3: SQLite CandidateStore

**Files:**
- Create: `backend/src/ontocore/candidates/__init__.py`
- Create: `backend/src/ontocore/candidates/store.py`
- Test: `backend/tests/test_candidate_store.py`

**Interfaces:**
- Consumes: `ExtractionResult`, `CandidateStatus`
- Produces:

```python
@dataclass
class StoredCandidate:
    id: str
    kind: Literal["class", "property", "instance", "relation"]
    job_id: str
    status: CandidateStatus
    payload: dict  # draft 字段 JSON

class CandidateStore:
    def __init__(self, sqlite_path: str) -> None: ...
    def replace_job_results(self, job_id: str, result: ExtractionResult) -> list[StoredCandidate]: ...
    def get(self, candidate_id: str) -> StoredCandidate: ...
    def list_by_job(self, job_id: str) -> list[StoredCandidate]: ...
    def set_status(self, candidate_id: str, status: CandidateStatus) -> StoredCandidate: ...
```

`replace_job_results` 删除该 job 旧行后插入，id 用 UUID。payload 对 class 含 iri/label/parent_iri/evidence/block_id/confidence。

- [ ] **Step 1: Write the failing test**

```python
from ontocore.candidates.store import CandidateStore
from ontocore.models import ClassCandidateDraft, ExtractionResult

def test_insert_and_accept(tmp_path):
    store = CandidateStore(str(tmp_path / "c.db"))
    result = ExtractionResult(
        class_candidates=[ClassCandidateDraft(iri="https://ontocore.local/ns/insurance-product#Foo", label="Foo", parent_iri=None, evidence="原文", block_id="b1", confidence=0.9)],
        property_candidates=[],
        instance_suggestions=[],
        relation_suggestions=[],
    )
    rows = store.replace_job_results("job1", result)
    assert rows[0].status == "proposed"
    updated = store.set_status(rows[0].id, "accepted")
    assert updated.status == "accepted"
    assert store.list_by_job("job1")[0].payload["evidence"] == "原文"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_candidate_store.py -v`

Expected: FAIL cannot import CandidateStore

- [ ] **Step 3: Write minimal implementation**

表 `candidates(id TEXT PRIMARY KEY, job_id TEXT, kind TEXT, status TEXT, payload_json TEXT)`。

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_candidate_store.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/ontocore/candidates backend/tests/test_candidate_store.py
git commit -m "feat: add SQLite candidate store"
```

---

### Task 4: 内存图、Projector、按 IRI 改显示名

**Files:**
- Create: `backend/src/ontocore/graph/__init__.py`
- Create: `backend/src/ontocore/graph/ports.py`
- Create: `backend/src/ontocore/graph/memory.py`
- Create: `backend/src/ontocore/graph/projector.py`
- Test: `backend/tests/test_projector.py`

**Interfaces:**
- Consumes: `TBoxSnapshot`, `GraphUnavailable`
- Produces:

```python
@dataclass
class GraphNode:
    onto_iri: str          # 实例 IRI 或合成 NS + local_id
    type_iri: str          # 类 IRI
    onto_label: str
    evidence: str
    block_id: str
    data: dict

@dataclass
class GraphRel:
    source_iri: str
    target_iri: str
    predicate_iri: str
    onto_label: str
    evidence: str
    block_id: str

class GraphRepository(Protocol):
    def upsert_node(self, node: GraphNode) -> None: ...
    def upsert_rel(self, rel: GraphRel) -> None: ...
    def get_node(self, onto_iri: str) -> GraphNode | None: ...
    def list_neighbors(self, onto_iri: str) -> list[tuple[GraphRel, GraphNode]]: ...
    def update_type_display(self, type_iri: str, onto_label: str) -> int: ...
    # 更新所有 type_iri 匹配的节点的 onto_label（类显示名同步）

class MemoryGraphRepository:
    ...

class Projector:
    def __init__(self, graph: GraphRepository) -> None: ...
    def register_type(self, type_iri: str, display_label: str) -> None: ...
    def display_label(self, type_iri: str) -> str: ...
    def project_instances(
        self,
        tbox: TBoxSnapshot,
        instances: list[InstanceSuggestionDraft],
        relations: list[RelationSuggestionDraft],
        *,
        iri_prefix: str,
    ) -> tuple[list[str], list[str]]:
        """返回 (projected_iris, skipped_reasons)。type 不在 tbox.classes 则 skip。"""
    def sync_class_label(self, type_iri: str, label: str) -> None: ...
```

原生 label 概念：`MemoryGraphRepository` 内部节点固定 `native_label="OntoNode"`，`update_type_display` **不得**改 `native_label`。测试断言改名后 `get_node` 仍用同一 `onto_iri`，`onto_label` 变了，`native_label` 仍为 `OntoNode`。

- [ ] **Step 1: Write the failing test**

```python
from ontocore.constants import NS
from ontocore.graph.memory import MemoryGraphRepository
from ontocore.graph.projector import Projector
from ontocore.models import InstanceSuggestionDraft, OwlClass, TBoxSnapshot

def test_skip_unconfirmed_type():
    g = MemoryGraphRepository()
    p = Projector(g)
    tbox = TBoxSnapshot(classes=(OwlClass(iri=f"{NS}Product", label="产品"),), properties=())
    inst = [InstanceSuggestionDraft(local_id="e1", type_iri=f"{NS}Unknown", label="x", data={}, evidence="e", block_id="b", confidence=1.0)]
    ok, skipped = p.project_instances(tbox, inst, [], iri_prefix=NS)
    assert ok == []
    assert skipped
    assert g.get_node(f"{NS}e1") is None

def test_sync_label_keeps_iri_and_native_label():
    g = MemoryGraphRepository()
    p = Projector(g)
    tbox = TBoxSnapshot(classes=(OwlClass(iri=f"{NS}Product", label="产品"),), properties=())
    inst = [InstanceSuggestionDraft(local_id="p1", type_iri=f"{NS}Product", label="某险", data={}, evidence="e", block_id="b", confidence=1.0)]
    p.project_instances(tbox, inst, [], iri_prefix=NS)
    p.sync_class_label(f"{NS}Product", "保险产品")
    node = g.get_node(f"{NS}p1")
    assert node is not None
    assert node.onto_label == "保险产品"
    assert g.native_label_of(f"{NS}p1") == "OntoNode"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_projector.py -v`

Expected: FAIL import Projector

- [ ] **Step 3: Write minimal implementation**

`project_instances`：确认 `type_iri` ∈ tbox 类 IRI 集合后 `upsert_node`，实例 IRI = `iri_prefix + local_id`。关系两端都必须已投影。`sync_class_label` 调 `register_type` + `graph.update_type_display`。

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_projector.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/ontocore/graph backend/tests/test_projector.py
git commit -m "feat: add graph projector with IRI display sync"
```

---

### Task 5: Neo4j GraphRepository 适配器

**Files:**
- Create: `backend/src/ontocore/graph/neo4j_repo.py`
- Create: `docker-compose.yml`
- Test: `backend/tests/test_neo4j_repo.py`

**Interfaces:**
- Consumes: `GraphRepository` 方法集合、`GraphNode`、`GraphRel`、`GraphUnavailable`
- Produces: `Neo4jGraphRepository(uri, user, password)` 实现同一 Protocol。Cypher 创建 `(:OntoNode {onto_iri, type_iri, onto_label, evidence, block_id, data_json})`，关系 `[:ONTO_REL {predicate_iri, onto_label, evidence, block_id}]`。`update_type_display`：`MATCH (n:OntoNode {type_iri:$t}) SET n.onto_label=$l`，**禁止** `REMOVE`/`SET` 动态 label。连接失败包装为 `GraphUnavailable`。

- [ ] **Step 1: Write the failing test**

无 `ONTOCORE_NEO4J_URI` 时 skip。有 URI 时跑与 Task 4 相同的 upsert/get/update_type_display 断言 `native` 通过固定 `:OntoNode`。

```python
import os
import pytest
from ontocore.constants import NS
from ontocore.graph.neo4j_repo import Neo4jGraphRepository
from ontocore.graph.ports import GraphNode

pytestmark = pytest.mark.skipif(
    not os.getenv("ONTOCORE_NEO4J_URI"),
    reason="Neo4j not configured",
)

def test_update_display_does_not_change_iri():
    g = Neo4jGraphRepository(os.environ["ONTOCORE_NEO4J_URI"], os.environ.get("ONTOCORE_NEO4J_USER", "neo4j"), os.environ.get("ONTOCORE_NEO4J_PASSWORD", "ontocore-test"))
    iri = f"{NS}neo4j-test-node"
    g.upsert_node(GraphNode(onto_iri=iri, type_iri=f"{NS}Product", onto_label="旧", evidence="e", block_id="b", data={}))
    g.update_type_display(f"{NS}Product", "新")
    node = g.get_node(iri)
    assert node.onto_label == "新"
    assert node.onto_iri == iri
```

把 `GraphNode` 放在 `ontocore.graph.ports`（Task 4 已定义则从此处导入，不要在 models.py 重复）。

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_neo4j_repo.py -v`

Expected: SKIP 或 FAIL `Neo4jGraphRepository` 不存在

- [ ] **Step 3: Write minimal implementation + compose**

`docker-compose.yml`：

```yaml
services:
  neo4j:
    image: neo4j:5
    ports: ["7474:7474", "7687:7687"]
    environment:
      NEO4J_AUTH: neo4j/ontocore-test
```

- [ ] **Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_neo4j_repo.py tests/test_projector.py -v`

Expected: projector PASS；neo4j SKIP 或 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/ontocore/graph/neo4j_repo.py backend/tests/test_neo4j_repo.py docker-compose.yml
git commit -m "feat: add Neo4j graph adapter with fixed OntoNode label"
```

---

### Task 6: DocumentIngress

**Files:**
- Create: `backend/src/ontocore/extract/__init__.py`
- Create: `backend/src/ontocore/extract/ingress.py`
- Test: `backend/tests/test_ingress.py`
- Test fixture files: `backend/tests/fixtures/sample.txt`

**Interfaces:**
- Consumes: `ParsedDocument`, `TextBlock`, `IngressError`
- Produces: `parse_bytes(filename: str, data: bytes) -> ParsedDocument`

规则：`.txt` 按空行和 Markdown 式 `#` 标题切块，`block_id` 为 `b-{index}`。空文本或仅空白 → `IngressError("无法提取文本")`。`.pdf` 用 pypdf；若 `len(text.strip())==0` 或加密 `is_encrypted` → `IngressError("无法提取文本")`。`.docx` 用 python-docx 段落。其它扩展名 → `IngressError("无法提取文本")`。

- [ ] **Step 1: Write the failing test**

```python
from ontocore.errors import IngressError
from ontocore.extract.ingress import parse_bytes

def test_txt_headings():
    doc = parse_bytes("a.txt", "保险责任\n\n给付癌症。\n\n除外责任\n\n不保流感。".encode("utf-8"))
    kinds = [b.kind for b in doc.blocks]
    assert "heading" in kinds or len(doc.blocks) >= 2
    assert "癌症" in doc.full_text

def test_empty_fails():
    try:
        parse_bytes("a.txt", b"   \n")
    except IngressError as e:
        assert "无法提取文本" in str(e)
        return
    raise AssertionError("expected IngressError")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_ingress.py -v`

Expected: FAIL import

- [ ] **Step 3: Write minimal implementation**

标题启发式：行长度 < 40 且无句号，或匹配 `^(第.+条|保险责任|除外责任|等待期)`。

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_ingress.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/ontocore/extract/ingress.py backend/tests/test_ingress.py backend/tests/fixtures
git commit -m "feat: parse txt/pdf/docx into text blocks"
```

---

### Task 7: LlmGateway（LiteLLM）与 FakeLlm

**Files:**
- Create: `backend/src/ontocore/extract/ports.py`
- Create: `backend/src/ontocore/extract/llm.py`
- Test: `backend/tests/test_llm_gateway.py`

**Interfaces:**
- Consumes: `StructuredOutputError`
- Produces:

```python
class LlmGateway(Protocol):
    def complete_structured(
        self,
        schema: dict,
        messages: list[dict[str, str]],
        *,
        model: str,
        max_retries: int = 2,
    ) -> dict: ...

class FakeLlm:
    def __init__(self, canned: dict) -> None: ...
    def complete_structured(self, schema, messages, *, model: str, max_retries: int = 2) -> dict: ...

class LiteLlmGateway:
    def complete_structured(self, schema, messages, *, model: str, max_retries: int = 2) -> dict: ...
```

`FakeLlm`：若 canned 无法通过 jsonschema 校验（手写：schema 要求的 required 字段缺失）抛 `StructuredOutputError`，**不得**返回半截 dict。`LiteLlmGateway` 调用 `litellm.completion`，`response_format` 为 json object；解析失败重试 `max_retries` 次后 `StructuredOutputError`。抽取器测试只用 `FakeLlm`。

- [ ] **Step 1: Write the failing test**

```python
from ontocore.errors import StructuredOutputError
from ontocore.extract.llm import FakeLlm

SCHEMA = {"type": "object", "required": ["classes"], "properties": {"classes": {"type": "array"}}}

def test_fake_returns_canned():
    llm = FakeLlm({"classes": []})
    assert llm.complete_structured(SCHEMA, [{"role": "user", "content": "x"}], model="fake") == {"classes": []}

def test_fake_rejects_bad_payload():
    llm = FakeLlm({"nope": 1})
    try:
        llm.complete_structured(SCHEMA, [{"role": "user", "content": "x"}], model="fake")
    except StructuredOutputError:
        return
    raise AssertionError("expected StructuredOutputError")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_llm_gateway.py -v`

Expected: FAIL import FakeLlm

- [ ] **Step 3: Write implementation**

校验：`required` 中每个 key 都在 dict 内即可（第一期不做完整 JSON Schema 引擎）。`LiteLlmGateway` 包一层 try/except Timeout/RateLimit 再重试。

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_llm_gateway.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/ontocore/extract/ports.py backend/src/ontocore/extract/llm.py backend/tests/test_llm_gateway.py
git commit -m "feat: add LiteLLM gateway and FakeLlm"
```

---

### Task 8: 领域包 + 抽取器插件（hybrid / llm_only / rules_only）

**Files:**
- Create: `backend/src/ontocore/domain/__init__.py`
- Create: `backend/src/ontocore/domain/insurance_product/pack.py`
- Create: `backend/src/ontocore/domain/insurance_product/seed.ttl`
- Create: `backend/src/ontocore/domain/insurance_product/fixture_excerpt.txt`
- Create: `backend/src/ontocore/extract/llm_only.py`
- Create: `backend/src/ontocore/extract/hybrid.py`
- Create: `backend/src/ontocore/extract/rules_only.py`
- Create: `backend/src/ontocore/extract/registry.py`
- Test: `backend/tests/test_domain_pack.py`
- Test: `backend/tests/test_extractors.py`

**Interfaces:**
- Consumes: `Extractor` Protocol、`TBoxSnapshot`、`ParsedDocument`、`LlmGateway`、`TBoxRepository.import_turtle`
- Produces:

```python
class DomainPack(Protocol):
    id: str
    def seed_turtle(self) -> str: ...
    def declared_type_iris(self) -> frozenset[str]: ...
    def heading_hints(self) -> tuple[str, ...]: ...

class InsuranceProductPack:
    id = "insurance-product"

class Extractor(Protocol):
    name: str
    def extract(self, doc: ParsedDocument, tbox: TBoxSnapshot, pack: DomainPack, llm: LlmGateway, *, model: str) -> ExtractionResult: ...

def get_extractor(name: str) -> Extractor: ...
```

种子 TTL 必须含 `Product`、`Coverage`、`Exclusion`、`WaitingPeriod` 四个 `owl:Class` 及中文 `rdfs:label`，可用对象属性 `:hasCoverage`、`:hasExclusion`、`:hasWaitingPeriod`。`assert_profile_turtle(seed)` 必须通过。

`llm_only`：一次 `complete_structured`，schema 为 classes/properties/instances/relations 数组；模型输出的未知类型进 `class_candidates`，实例 `type_iri` 可指向 proposed IRI。

`hybrid`：先按 `heading_hints`（含「保险责任」「除外」「等待期」「产品」）切段；每段调用 LLM 只抽该段 instances；标题「除外责任」对齐 `Exclusion`。块级 `StructuredOutputError` 写入 `block_failures`，其它块继续。

`rules_only`：无 LLM。标题匹配映射到声明类型，段落第一句作为实例 label；`type_iri` 只用 `declared_type_iris()`。

- [ ] **Step 1: Write the failing tests**

`test_domain_pack.py`：加载 seed，`assert_profile_turtle`，四类 IRI 都在 snapshot（经临时 `TBoxRepository.import_turtle(force=True)`）。

`test_extractors.py`：`FakeLlm` 固定返回一个新类 `FooBar` 和一个 `Product` 实例；`get_extractor("llm_only").extract(...)` 结果含 class candidate 与 instance；`get_extractor("hybrid")` 在「除外责任\n\n不保流感」文档上至少有一个 instance 或 class，且 `block_failures` 为 list；抽取后 TBoxRepository 仍无 `FooBar`（证明未写库）。

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_domain_pack.py tests/test_extractors.py -v`

Expected: FAIL missing modules

- [ ] **Step 3: Write seed, pack, three extractors, registry**

`fixture_excerpt.txt` 写 8～15 行脱敏说明书片段（责任/除外/等待期各一段），供 Task 12 回归。

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_domain_pack.py tests/test_extractors.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/ontocore/domain backend/src/ontocore/extract backend/tests/test_domain_pack.py backend/tests/test_extractors.py
git commit -m "feat: add insurance domain pack and pluggable extractors"
```

---

### Task 9: JobStore、抽取编排、审阅事务与图投影重试

**Files:**
- Create: `backend/src/ontocore/jobs/__init__.py`
- Create: `backend/src/ontocore/jobs/store.py`
- Create: `backend/src/ontocore/jobs/service.py`
- Create: `backend/src/ontocore/review/__init__.py`
- Create: `backend/src/ontocore/review/service.py`
- Test: `backend/tests/test_review_and_jobs.py`

**Interfaces:**
- Consumes: 此前全部 Repository/Extractor/Ingress
- Produces:

```python
@dataclass
class Job:
    id: str
    status: JobStatus
    extractor: str
    model: str
    domain_pack: str
    filename: str
    error: str | None
    tbox_snapshot_at_start: str  # turtle 备份可选，可空

class JobStore:
    def create(...) -> Job: ...
    def update_status(self, job_id: str, status: JobStatus, error: str | None = None) -> Job: ...
    def get(self, job_id: str) -> Job: ...

class JobService:
    def __init__(self, jobs, candidates, tbox, ingress, extractors, llm, pack): ...
    def run(self, job_id: str, filename: str, data: bytes) -> Job: ...
    # parse → extract(只读 tbox.snapshot()) → candidates.replace_job_results
    # 全失败 failed；仅部分块失败 partial；成功 completed
    # StructuredOutputError/厂商错误：重试 complete_structured 已在 gateway；此处捕获后 failed 且保留已写入候选（无候选则 failed）

class ReviewService:
    def __init__(self, tbox: TBoxRepository, candidates: CandidateStore, projector: Projector): ...
    def accept_class(self, candidate_id: str) -> None: ...
    def reject_class(self, candidate_id: str) -> None: ...
    def accept_property(self, candidate_id: str) -> None: ...
    def project_job_instances(self, job_id: str) -> tuple[list[str], list[str]]: ...
    def retry_projection(self, job_id: str) -> tuple[list[str], list[str]]: ...
```

`accept_class`：`set_status accepted` 与 `tbox.create_class` 同一把 tbox 锁内完成；失败则候选保持 proposed（先 create 成功再 set_status，create 失败不改 status）。`reject_class` 后 `project_job_instances` 不得为该 type 建节点。`project_job_instances` 只投影 type 已在 `tbox.snapshot()` 中的 instance；图抛 `GraphUnavailable` 时由 JobService 把 job 设为 `tbox_accepted_graph_pending`。

用会抛 `GraphUnavailable` 的 FakeGraph 测 pending。

- [ ] **Step 1: Write the failing test**

```python
from ontocore.constants import NS
from ontocore.errors import GraphUnavailable
from ontocore.graph.memory import MemoryGraphRepository
from ontocore.graph.projector import Projector
from ontocore.models import ClassCandidateDraft, ExtractionResult, InstanceSuggestionDraft, OwlClass
from ontocore.review.service import ReviewService
from ontocore.tbox.repository import TBoxRepository
from ontocore.candidates.store import CandidateStore

class BoomGraph(MemoryGraphRepository):
    def upsert_node(self, node):
        raise GraphUnavailable("down")

def test_accept_writes_owl_reject_skips_graph(tmp_path):
    tbox = TBoxRepository()
    tbox.create_class(OwlClass(iri=f"{NS}Product", label="产品"))
    cstore = CandidateStore(str(tmp_path / "c.db"))
    result = ExtractionResult(
        class_candidates=[ClassCandidateDraft(iri=f"{NS}Rider", label="附加险", parent_iri=None, evidence="e", block_id="b", confidence=1)],
        property_candidates=[],
        instance_suggestions=[
            InstanceSuggestionDraft(local_id="r1", type_iri=f"{NS}Rider", label="附加", data={}, evidence="e", block_id="b", confidence=1),
            InstanceSuggestionDraft(local_id="p1", type_iri=f"{NS}Product", label="主险", data={}, evidence="e", block_id="b", confidence=1),
        ],
        relation_suggestions=[],
    )
    rows = cstore.replace_job_results("j1", result)
    class_id = next(r.id for r in rows if r.kind == "class")
    graph = MemoryGraphRepository()
    review = ReviewService(tbox, cstore, Projector(graph))
    review.reject_class(class_id)
    review.project_job_instances("j1")
    assert graph.get_node(f"{NS}r1") is None
    assert graph.get_node(f"{NS}p1") is not None
    assert all(c.iri != f"{NS}Rider" for c in tbox.snapshot().classes)

def test_accept_then_owl_has_class(tmp_path):
    tbox = TBoxRepository()
    cstore = CandidateStore(str(tmp_path / "c.db"))
    result = ExtractionResult(
        class_candidates=[ClassCandidateDraft(iri=f"{NS}Rider", label="附加险", parent_iri=None, evidence="e", block_id="b", confidence=1)],
        property_candidates=[], instance_suggestions=[], relation_suggestions=[],
    )
    cid = cstore.replace_job_results("j2", result)[0].id
    review = ReviewService(tbox, cstore, Projector(MemoryGraphRepository()))
    review.accept_class(cid)
    assert any(c.iri == f"{NS}Rider" for c in tbox.snapshot().classes)
```

另写：

- `test_job_run_empty_file_failed`：`JobService.run` 对空 txt 状态 `failed`，error 含「无法提取文本」。
- `test_projection_sets_graph_pending`：`ReviewService.project_job_instances` 在 `BoomGraph` 上捕获 `GraphUnavailable` 后，由 `JobStore.update_status(..., "tbox_accepted_graph_pending")`（可在 ReviewService 返回特殊结果或抛错由 JobService 封装；测试断言 job.status == `tbox_accepted_graph_pending`）。

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_review_and_jobs.py -v`

Expected: FAIL import ReviewService

- [ ] **Step 3: Implement JobStore (SQLite 可与 candidates 同文件不同表)、JobService、ReviewService**

`run` 开始 `running`。LLM 异常：status `failed`，若 extract 已返回部分 result 仍 `replace_job_results`。

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_review_and_jobs.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/ontocore/jobs backend/src/ontocore/review backend/tests/test_review_and_jobs.py
git commit -m "feat: add extraction jobs and TBox review transactions"
```

---

### Task 10: FastAPI 与设置

**Files:**
- Create: `backend/src/ontocore/settings.py`
- Create: `backend/src/ontocore/api/__init__.py`
- Create: `backend/src/ontocore/api/app.py`
- Test: `backend/tests/test_api.py`

**Interfaces:**
- Consumes: JobService、ReviewService、TBoxRepository、Projector
- Produces: `create_app(...) -> FastAPI`

路由：

- `GET /api/settings` → `{extractors, models, domain_packs, default_extractor}`
- `PUT /api/settings` → 保存默认 extractor/model（SQLite 或 json 文件 `data/settings.json`）
- `POST /api/jobs` multipart file + extractor + model + domain_pack → 同步 `run`（第一期不做队列进程）返回 Job
- `GET /api/jobs/{id}`
- `GET /api/jobs/{id}/candidates`
- `POST /api/candidates/{id}/accept` body 可选 `{iri, label}` 覆盖后再 accept
- `POST /api/candidates/{id}/reject`
- `POST /api/jobs/{id}/project`
- `POST /api/jobs/{id}/project/retry`
- `POST /api/tbox/classes` JSON `{iri?, label, parent_iri?}` 缺省 iri 用 NS + 拼音或 slug（可用 label 的英文 stub：调用方必填 `local_name`）
- `POST /api/tbox/properties` `{local_name, label, kind, domain_iri?, range_iri?}`
- `PATCH /api/tbox/classes/label` `{iri, label}` → `update_label` + `projector.sync_class_label`
- `GET /api/tbox/snapshot`
- `GET /api/tbox/export?format=turtle|jsonld`
- `POST /api/tbox/import?force=false` body turtle
- `GET /api/graph/nodes/{onto_iri}`
- `GET /api/graph/browse?root_iri=` 邻居

手工建类请求：`local_name` 必填，IRI = NS + local_name。

- [ ] **Step 1: Write the failing test**

使用 `fastapi.testclient.TestClient` + 内存依赖（MemoryGraph、临时 sqlite、FakeLlm 注入）。测：POST 空文件 → 200/400 且 status failed；POST 手工类 → snapshot 含该类；import 无 force 第二次 400。

```python
from fastapi.testclient import TestClient
from ontocore.api.app import create_app
from ontocore.constants import NS

def test_manual_class_and_import_conflict(tmp_path, monkeypatch):
    app = create_app(data_dir=tmp_path)
    c = TestClient(app)
    r = c.post("/api/tbox/classes", json={"local_name": "ManualX", "label": "手工类"})
    assert r.status_code == 200
    ttl = c.get("/api/tbox/export", params={"format": "turtle"}).text
    r2 = c.post("/api/tbox/import", params={"force": "false"}, content=ttl, headers={"content-type": "text/turtle"})
    assert r2.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_api.py -v`

Expected: FAIL import create_app

- [ ] **Step 3: Implement create_app 与路由；TBoxWriteError → HTTP 400**

默认图用 Memory；环境变量 `ONTOCORE_NEO4J_URI` 存在则换 Neo4j。CORS 允许 localhost 前端。

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_api.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/ontocore/settings.py backend/src/ontocore/api backend/tests/test_api.py
git commit -m "feat: add FastAPI for jobs, review, tbox, and graph query"
```

---

### Task 11: 前端五页

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`（proxy `/api` → `http://127.0.0.1:8000`）
- Create: `frontend/tsconfig.json`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/api.ts`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/pages/UploadPage.tsx`
- Create: `frontend/src/pages/ReviewPage.tsx`
- Create: `frontend/src/pages/TBoxPage.tsx`
- Create: `frontend/src/pages/GraphPage.tsx`
- Create: `frontend/src/pages/SettingsPage.tsx`
- Test: `frontend/src/api.test.ts`

**Interfaces:**
- Consumes: Task 10 JSON 形状
- Produces: 可运行 UI

页面：上传（选 extractor/model/pack、进度/status/error）；候选列表接受/拒绝/改 label 与 iri；手工建类属性；图浏览（输入 root 或从 Product 列表点选，展示邻居 `onto_label`）；设置。接受后提供「投影到图」按钮。TBox 页改 label 调 PATCH 同步。

- [ ] **Step 1: Write the failing test**

`api.ts` 导出 `acceptCandidate(id, body)` URL 为 `/api/candidates/${id}/accept`。Vitest：

```ts
import { acceptUrl } from "./api";
import { expect, test } from "vitest";
test("accept url", () => {
  expect(acceptUrl("abc")).toBe("/api/candidates/abc/accept");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm install && npx vitest run src/api.test.ts`

Expected: FAIL missing file

- [ ] **Step 3: Scaffold Vite React 与页面**

`package.json` scripts: `"dev": "vite"`, `"test": "vitest run"`。依赖：react、react-dom、vite、vitest。

- [ ] **Step 4: Run vitest**

Run: `cd frontend && npm test`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend
git commit -m "feat: add web UI for upload, review, tbox, graph, settings"
```

---

### Task 12: Fixture 回归与 README

**Files:**
- Modify: `backend/src/ontocore/domain/insurance_product/fixture_excerpt.txt`（若 Task 8 已写则只加测试）
- Test: `backend/tests/test_fixture_regression.py`
- Create: `README.md`

**Interfaces:**
- Consumes: JobService、FakeLlm 返回与 fixture 对齐的结构化结果
- Produces: 不设准确率断言；只断言跑完 status 为 `completed` 或 `partial`，且 candidates 非空。

- [ ] **Step 1: Write the failing test**

读取 `fixture_excerpt.txt`，`JobService.run` 使用 `rules_only`（不依赖外网）。断言 job.status in (`completed`,`partial`) 且 list_by_job 长度 ≥ 1。

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_fixture_regression.py -v`

Expected: FAIL 直至 JobService 接好 rules_only

- [ ] **Step 3: README**

说明：`pip install -e backend/.[dev]`、`uvicorn ontocore.api.app:app` 需暴露 `create_app` 的模块级 `app = create_app()`；`npm run dev`；可选 `docker compose up neo4j`；LiteLLM 环境变量 `OPENAI_API_KEY` 等。

`app.py` 增加 `app = create_app()` 默认 `data_dir=./data`。

- [ ] **Step 4: Run full backend tests**

Run: `cd backend && python -m pytest -v`

Expected: 除 neo4j skip 外全部 PASS

- [ ] **Step 5: Commit**

```bash
git add README.md backend/tests/test_fixture_regression.py backend/src/ontocore/api/app.py
git commit -m "docs: add runbook and fixture regression for insurance excerpt"
```

---

## Self-review vs spec

| Spec 项 | Task |
| --- | --- |
| 上传说明书 PDF/DOCX/TXT、无 OCR | 6, 10, 11 |
| 可插拔抽取器 hybrid/llm_only/rules_only | 8, 9 |
| LiteLLM 多厂商 | 7, 10 settings |
| 候选人审后 OWL | 9, 10 |
| 手工建类/属性 | 2, 10, 11 |
| 实例进图、未确认类型跳过 | 4, 9 |
| Turtle/JSON-LD 导入默认不覆盖 | 2, 10 |
| IRI + onto_label 同步、不改原生 label | 4, 5, 10 PATCH |
| 领域包四类 + seed 剖面 | 8 |
| Job failed/partial/graph_pending | 9 |
| 必做测试清单 | 2, 4, 8, 9, 12 |
| 模块化单体 Python+TS | 10–11 |
| 不做 OCR/评测门槛/完整编辑器 | 未列入任务 |

无 TBD/TODO 占位。类型名以 Task 1 `models.py` 与 Task 4 `graph.ports.GraphNode` 为准；API 测试从 `ports` 导入 `GraphNode`，不要在 `models.py` 再定义一份。
