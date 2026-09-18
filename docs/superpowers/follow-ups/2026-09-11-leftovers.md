# 未完成项（相对现行规格与代码）

日期：2026-09-15（相对 2026-09-11 原稿按当前仓库重核）  
对照：[`../specs/2026-09-15-ontocore-objects-relations-design.md`](../specs/2026-09-15-ontocore-objects-relations-design.md) §12。  
实现核对：`backend/src/`、`frontend/src/`、`README.md`、`frontend/package.json`。

## 规格写了、实现仍缺

1. **审阅时改显示名 / 本地名**（规格 §6 / §12）  
   `ReviewPage` 只有接受 / 拒绝 / 投影，候选 `payload` 只展示，没有改名接口。

2. **作业级有限次重试**（规格 §8 / §12）  
   `JobService.run` 解析失败或抽取/LLM 异常直接 `failed`；超时/429 无重试。`/api/settings/test` 虽把 429 映射成中文，作业路径不走该逻辑。

3. **JSON-LD 导入**（规格要求 Turtle 与 JSON-LD 导入导出）  
   `GET /api/ontology/export?format=jsonld` 可导出；`POST /api/ontology/import` 只 `import_turtle`。

4. **错误信息全中文**（产品语言）  
   `ontology/repository.py`、`ontology/profile.py` 仍抛英文（如 `IRI already exists`、`predicate not allowed`）。API `_write_detail` 做单词替换，仍会中英混杂。内部 OWL 剖面词仅应留在仓库层。

5. **审阅 `?job=` 自动加载候选**（规格 §12）  
   `ReviewPage` 用 `useSearchParams` 把 `job` 填进输入框，没有 `useEffect` 自动 `typeCandidates`。上传成功跳到 `/review?job=` 后仍要点「加载候选」。

6. **前端 `build` 跑 `tsc`；页面级行为测试仍薄**（规格 §9 / §12）  
   `frontend/package.json` 的 `build` 仍是 `vite build`。`api.test.ts` 是源码扫描（文案、接线、弹窗、`has_api_key`），没有组件/浏览器行为测。

## 文档与体验（代码已变、文档或边角未跟上）

- **README 数据目录**：仍写「数据目录默认临时目录」。实现是 `ONTOCORE_DATA_DIR`，缺省相对后端工作目录的 `./data`（开发时多为 `backend/data/`）。测试才用 pytest 临时目录。
- **README 密钥**：仍写 `OPENAI_API_KEY`。现行设置把模型供应商放进 `ontocore.db` 密文 + `master.key` / `ONTOCORE_SECRET_KEY`；`GET /api/settings` 只给 `has_api_key`。
- 上传页文案仍是「供应商」，设置页已是「模型供应商」。
- 文档解析仍只做 `.txt` / `.pdf`（pypdf 抽字）/ `.docx`；无 OCR（规格 §11，不是漏做）。

## 实现边角（规格未单列，代码里仍在）

- **属性占用检查键可能对不上实例 `data`**：`count_nodes_with_attribute` 用属性 **IRI** 做 `node.data` 的键；抽取实例 `data` 常来自模型，键可能是显示名。删属性时可能漏拦或误拦。
- **候选 IRI 未强制工作本体前缀**：`rules_only` 会拼 `NS + local`；`llm_only` / `hybrid` 信任模型返回的 `iri`，未校验 `https://ontocore.local/ns/working#`。
- **Neo4j 适配器无连接池**：`Neo4jGraphRepository._with_session` 每次 `GraphDatabase.driver(...)` 再 `close()`。
- **Oxigraph 本机易损坏**：已改为 `ontology.nq` 原子快照 + 内存 Store；异常关闭不再依赖 RocksDB 目录。旧 `oxigraph/` 仅作一次性迁移。

## 已从本清单划掉（对照 2026-09-11 之后已落地，勿再当缺口）

- 本体页：新建对象/关系、对象与关系详情走弹窗；主页面对象关系网（无对象列表）。
- 设置页：模型供应商卡片网格；新增/编辑弹窗；去掉点状空占位。
- 模型供应商：SQLite 密文；接口不回传 `api_key`；页面不回填、不写 `localStorage`。
- 设置页 tips、Dify 浅色工作台、新建对象可附带可选属性：已在现行页里。

## 明确不做（规格 §11，不是遗漏）

领域包、OCR、实例逐条审阅、关系多起点/多终点、完整公理编辑器、生产 SDK、抽取准确率门槛、`develop` / `release` 分支流程。
