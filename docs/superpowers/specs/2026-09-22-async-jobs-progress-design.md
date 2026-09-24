# OntoCore 设计：异步作业、全量列表与切片进度

日期：2026-09-22（2026-09-23：状态与分阶段进度以 [`2026-09-23-job-dedup-status-design.md`](2026-09-23-job-dedup-status-design.md) 为准）  
状态：已确认（进度/状态细则见 2026-09-23；本文保留列表交互与异步接口）  
范围：数据源页作业可见性；`POST /api/jobs` 异步；全量作业列表；进度展示  
相关：[`2026-09-15-ontocore-objects-relations-design.md`](2026-09-15-ontocore-objects-relations-design.md)、[`2026-09-20-extraction-engine-design.md`](2026-09-20-extraction-engine-design.md)、[`2026-09-21-fault-logging-design.md`](2026-09-21-fault-logging-design.md)、[`2026-09-23-job-dedup-status-design.md`](2026-09-23-job-dedup-status-design.md)

## 1. 目标

点「开始抽取」前后用户都能看到作业：主界面是**全部作业列表**；新建走弹窗；点行打开作业卡。后台跑抽取 / 合并 / 判重时，界面可轮询**状态与当前阶段进度**（口径见 [`2026-09-23-job-dedup-status-design.md`](2026-09-23-job-dedup-status-design.md)）。

## 2. 异步执行

**本轮**

- `POST /api/jobs`：校验通过后**只保存作业**（`queued`）并落盘上传文件，**不**自动开始抽取；立即返回。
- `POST /api/jobs/{id}/start`：对可启动状态调度全链路（解析 → 切块抽取 → 作业内合并 → 对库判重）；进程内线程池执行；立即返回。可启动集合与重置规则见 2026-09-23 §3 / §7。  
- 校验失败仍同步 400，文案走故障码对照表。  
- 进程重启：将仍为进行中（`extracting` / `merging` / `aligning`，含旧码 `running`）的作业标为 `failed`，`error` 为「服务已重启，请重新抽取」（`OC-3108`）。已保存未启动的 `queued` **保留**。

**后续升级（本轮不做实现）**

- 用 **Celery**（或同类 broker + worker）替换进程内线程池。
- 对外尽量保持：`POST /api/jobs`、`POST /api/jobs/{id}/start`、`GET /api/jobs`、`GET /api/jobs/{id}` 的语义与字段形状；仅把「谁执行 `JobService.run`」从线程改为 Celery task。
- 本轮不引入 Redis/RabbitMQ、Celery 依赖或部署文档。

## 3. 接口

| 方法 | 行为 |
| --- | --- |
| `POST /api/jobs` | 创建作业并保存上传文件；`status=queued`；不调度抽取 |
| `PATCH /api/jobs/{id}` | **仅 `queued`**：更新供应商/模型/thinking/嵌入/引导；可选替换上传文件。其它状态 400（`OC-1109`） |
| `POST /api/jobs/{id}/start` | 调度全链路；允许集合与进行中拒绝见 2026-09-23；非 `queued` 的可重抽状态先重置进度与错误 |
| `GET /api/jobs` | **全部**作业，默认按创建时间**倒序**（新在前）。本轮不分页、不筛选 |
| `GET /api/jobs/{id}` | 单条作业；前端轮询用 |

上传文件保存在数据目录下（如 `uploads/{job_id}`），供启动时读取。

作业需有可排序的创建时间（如 `created_at`）；旧行无时间则排后或用既有可推断顺序，迁移时补列。

进度字段与分阶段口径以 [`2026-09-23-job-dedup-status-design.md`](2026-09-23-job-dedup-status-design.md) §3–§4 为准（`progress_done` / `progress_total` 随阶段变义）。

另：`OC-1107` 当前状态不能启动抽取；`OC-1108` 上传文件已丢失，请重新新建作业；`OC-1109` 当前状态不能修改作业。

## 4. 切片规则

切块规则与现行抽取引擎一致（见 [`2026-09-20-extraction-engine-design.md`](2026-09-20-extraction-engine-design.md) §4.2）。**抽取阶段**进度按切片计；合并与判重进度见 2026-09-23 §4。

## 5. 数据源页交互

- **主界面**：全部作业列表（时间倒序）。顶栏「数据源」+「新建抽取」。空态：「还没有作业」+ 同一入口。  
- **新建**：按钮打开**弹窗**，内为现有表单（文件、抽取/嵌入供应商与模型、thinking、选择引导）。提交按钮文案为「保存作业」：只创建 `queued` 作业，**不**启动抽取。成功 tips「作业已保存」，关弹窗、刷新列表。  
- **列表操作**：`queued` / `failed` 为高亮文案「启动抽取」（非按钮）；`reviewable` / `reviewable_partial`（及兼容旧码）为高亮「审阅」；进行中为「—」。点操作文案不打开详情。  
- **详情**：点列表一行（非操作文案）打开作业卡。  
  - **`queued`**：可编辑表单（文件可选替换、供应商/模型、thinking、引导）+「保存修改」（`PATCH`）+「启动抽取」。  
  - **待审阅**：只读展示抽取模型、嵌入模型、引导对象/关系等；「审阅」「重新抽取」。  
  - **失败**：可「启动抽取」/「重新抽取」。  
- 列表列：**作业编号**、文件、状态、进度、创建时间、**操作**（无模型列）。列表与表单下拉过长文案省略，悬停展示全文。  
- **进度**：只显示百分比（不显示 done/total）；口径见 2026-09-23 §4。  

| status | 展示 |
| --- | --- |
| queued | 待启动 |
| extracting（含旧 running） | 抽取中 |
| merging | 合并中 |
| aligning | 判重中 |
| reviewable（含旧 completed） | 待审阅 |
| reviewable_partial（含旧 partial） | 待审阅 |
| failed | 失败 |
| types_accepted_graph_pending | 待投影 |

## 6. 测试与验收

- `POST /api/jobs` 返回 `queued`；`POST .../start` 后进入进行中或终态（见 2026-09-23）。  
- `GET /api/jobs` 含全部作业且新在前。  
- 分阶段进度与作业内去重验收见 2026-09-23 §8。  
- 前端：列表「启动抽取」/「审阅」；新建「保存作业」；待启动可 PATCH；进行中可见阶段状态与进度。  
- 不打真实供应商。

## 7. 不做（本轮）

- Celery / 外部 broker 落地（仅规格预留）  
- 作业删除、筛选、分页  
- WebSocket  
- 作业级自动重试（仍见对象关系规格 §12）  
- 去重与新状态机的实现细节以 2026-09-23 为准；本文不重复展开