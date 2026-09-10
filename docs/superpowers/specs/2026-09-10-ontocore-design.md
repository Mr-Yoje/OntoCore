# OntoCore 第一期设计：本体仓库 + 保险产品说明书抽取

日期：2026-09-10  
状态：待用户审阅  
范围：模块化单体的最小可演示基础设施（非结构化文本这一路数据源）

## 1. 背景与目标

OntoCore 是本体管理基础设施：长期要管理本体、从多路数据源抽取，并同时服务知识工程师与业务系统。本仓库从空项目起步。

第一期只做一条可演示闭环：**上传保险产品说明书 → 可插拔抽取 → 人审候选 TBox → 权威 OWL + 实例图 → 简易浏览与 OWL 导入导出 → TBox 变更到图的最小同步**。知识工程师完整编辑器、生产级多语言 SDK、除文本外的数据源均不在本期。

成功标准（必达）：

- 用户可上传 1～2 份中文保险产品说明书（可含条款章节）。
- 系统产出候选类/关系与建议实例；人确认后写入 OWL；类型已确认的实例写入属性图并可浏览。
- 支持手工创建类/属性，且后续抽取能对齐到手工 TBox。
- OWL 可导出（Turtle / JSON-LD）并再导入。
- 可演示一次 TBox 到图的映射同步（显示名/映射更新后仍能按 IRI 找到节点）。

明确不做：OCR、抽取准确率门槛、多租户与权限矩阵、工作流引擎、全量 OWL 2 DL 推理、评测集 CI。

## 2. 长期模型：A2 + OWL 小剖面

权威分层：

- **TBox（唯一模式真相）**：RDF + 受约束的 OWL 剖面，存嵌入式 RDF 库。
- **ABox（实例真相）**：属性图（Neo4j），节点/边类型必须映射到已确认 TBox。
- 属性图不是模式权威；图库不可用时不得把实例写进 OWL 充数。

OWL 小剖面（第一期只实现这些构件）：

- 类、`rdfs:subClassOf` 层次
- 对象属性、数据属性、`rdfs:domain` / `rdfs:range`
- 可选：简单 `owl:disjointWith`（两个命名类）
- 个体不作为 TBox 权威的一部分；个体只进图

禁止第一期写入：复杂匿名类、一般角色包含、完整 OWL 2 DL 约束。序列化从第一天使用 Turtle / JSON-LD，避免自有 JSON 成为权威格式。

第一期只维护 **一个** 工作本体，id 为 `insurance-product`。类与属性 IRI 默认前缀：`https://ontocore.local/ns/insurance-product#`。手工创建与接受候选时可改本地名，但一旦确认，IRI 视为稳定主键；改名默认只改 `rdfs:label` / 图侧 `onto_label`，改 IRI 视为迁移（第一期 UI 可提供，实现上更新 OWL 主体并改映射表，不在图里靠原生 label 当主键）。

## 3. 架构

Python 后端 + TypeScript Web 的模块化单体。核心通过端口交互，适配器可替换。

四块核心：

1. **TBox 服务**：手工提交与「已接受候选」写入权威 OWL；导出/导入。
2. **ABox 图服务**：仅投影已确认类型上的实例与关系。
3. **抽取编排**：文档解析 → 抽取器插件 → LiteLLM 结构化调用 → 候选结果。
4. **同步器（Projector）**：维护 `TBox IRI ↔ 图类型/显示属性`；变更更新映射与节点上的显示属性，不把 Neo4j 原生 label 当作可随意重命名的主键。

领域包、抽取器、LLM 厂商、RDF 实现、图库均为插件边界。第一期只装配：一个保险产品领域包、`hybrid` + `llm_only` 抽取器（预留 `rules_only`）、LiteLLM 多厂商、嵌入式 RDF、Neo4j、SQLite 作业元数据。

## 4. 组件与接口

### 4.1 DocumentIngress

- 输入：PDF、DOCX、纯文本。
- 输出：规范化纯文本 + 结构块（标题、段落、列表），块带稳定 `block_id`。
- 加密 PDF、空文本、扫描件无文字：作业失败，提示无法提取文本。第一期不做 OCR。

### 4.2 Extractor 插件

统一接口（逻辑形状，实现时用 Python Protocol）：

`extract(doc, tbox_snapshot, domain_pack, llm) → ExtractionResult`

- `ExtractionResult` 只含候选，抽取器不得写 TBox 或图。
- 内置：`hybrid`（默认，规则/版式切块 + LLM 类型绑定与关系）、`llm_only`；预留 `rules_only`。
- 作业或全局配置选择抽取器。

### 4.3 LLM Gateway（LiteLLM）

- 抽取器只调用 `complete_structured(schema, messages)`。
- 底层用 LiteLLM 路由 OpenAI 兼容、国内云、本地端点；作业级或全局配置厂商与模型名。
- 禁止在抽取器内直接引用某一厂商 SDK。

### 4.4 CandidateStore

- 候选类、候选属性、建议实例；每条带证据（原文片段、`block_id`、置信度）。
- 状态：`proposed` / `accepted` / `rejected`。
- 不合 schema 的模型输出不得入库。

### 4.5 TBoxRepository

- 写入来源仅三路：手工 API、候选 accepted、OWL 导入。
- 导入默认：同 IRI 已存在则拒绝覆盖，除非请求显式 `force=true`。
- 同一本体同一时刻仅一个确认/导入写事务；抽取只读 TBox 快照。

### 4.6 GraphRepository 与 Projector

- 图写入仅来自：所用类型均已在权威 TBox 中的建议 ABox。
- Projector 登记 IRI ↔ 图侧类型名，并在节点/边上写 `onto_iri`、`onto_label`（显示名）。
- 第一期同步演示：修改已确认类的显示名或映射名 → 更新映射表与 `onto_label`；查询 API 返回新显示名；节点仍按 `onto_iri` 查找。不重写 Neo4j 原生 label 作为同步手段。

### 4.7 HTTP API 与前端

API（同一后端）：上传与作业状态、审候选、手工建类/属性、只读 TBox/图查询、导出导入、抽取器/模型/领域包设置。

前端页面：上传与进度、候选审阅（接受/拒绝/改本地名或 IRI）、手工建类与属性（父类、domain/range）、简易图浏览、设置。

不做完整公理编辑器。

## 5. 领域包：insurance-product

架构按可插拔领域包；第一期只带 **保险产品与条款** 切片，不覆盖理赔、再保、投顾全链路。

领域包提供：

- 种子 OWL（小剖面内）
- 说明书解析提示：目录、责任/除外等小标题的规则与示例
- 声明的目标类型（至少包括，可用中文 rdfs:label、稳定英文 IRI 本地名）：
  - `Product`（保险产品/险种）
  - `Coverage`（保险责任）
  - `Exclusion`（除外责任）
  - `WaitingPeriod`（等待期）
- 未声明而模型提出的类型进入「建议新类」，不得直接作为图 label

语料：用户上传的产品说明书，而非仅精选条款 PDF。

## 6. 数据流

1. 用户选择领域包、抽取器、LiteLLM 模型，上传说明书 → Job `queued`。
2. 解析成功则进入抽取；失败则 `failed`。
3. 抽取器读取当前权威 TBox 快照 + 种子：能对齐则对齐，否则 `proposed` 类/属性。
4. 在「权威 TBox ∪ 本次 proposed」上生成建议实例与关系，写入 CandidateStore，不写 Neo4j。
5. 人审 TBox：接受则事务内写 OWL 并登记映射；拒绝则该类型不得用于权威图投影。
6. 投影 ABox：跳过未确认类型并列出原因；证据以属性或旁路表挂到图元，便于回溯原文。
7. 浏览走 TBox + 图查询。导出 Turtle/JSON-LD。
8. 改显示名/映射名后查询展示更新，IRI 稳定。

作业状态还包括：`partial`（部分块失败仍可审已成功块）、`tbox_accepted_graph_pending`（图不可用，投影可单独重试）。已确认 OWL 不因后续抽取失败而自动回滚。

## 7. 错误处理

- 模型超时、429、厂商错误：作业级有限次重试；仍失败则 `failed`，已有候选保留，允许换模型重跑同一文档。
- 结构化输出校验失败：该块失败，作业可为 `partial`。
- TBox 写入：IRI 冲突、父类不存在、domain/range 指向未知类 → HTTP 400，事务不提交。
- 图写入：未确认类型跳过；Neo4j 宕机则停在 `tbox_accepted_graph_pending`。
- 不引入跨 RDF 与 Neo4j 的分布式事务；顺序为先权威 TBox，后图投影，图失败可重试。

## 8. 测试

必做：

- 种子 OWL 可加载且仅含小剖面构件。
- 抽取器契约：假 LLM 固定输出时，`hybrid` 与 `llm_only` 产出合法 `ExtractionResult`。
- 审阅事务：接受后 OWL 含该类；拒绝后图投影不含该类型实例。
- 导入：无 `force` 时同 IRI 拒绝。
- 同步：改映射后 API 显示新名，按 IRI 仍能找到节点。
- 一份脱敏说明书片段 fixture，作回归演示，不设准确率门槛。

## 9. 技术选型（第一期默认）

| 部分 | 选择 |
| --- | --- |
| 后端 | Python |
| 前端 | TypeScript |
| LLM | LiteLLM 多厂商 |
| TBox 存储 | 嵌入式 RDF，默认 Oxigraph，经 Repository 接口隔离 |
| ABox 存储 | Neo4j |
| 作业/候选元数据 | SQLite |
| 默认抽取 | hybrid |

以后可拆抽取集群或独立 OWL 服务，不作为第一期交付。

## 10. 非目标与后续

后续（不在本期计划中展开实现）：多数据源适配器、评测集与指标、OCR、完整编辑器、业务 SDK、更多领域包、推理引擎、流水线平台（Prefect/Airflow）、TBox 与图双写分布式事务。
