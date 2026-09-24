# OntoCore 设计：故障码与日志排查

日期：2026-09-21（2026-09-22 细化码表与固定文案）  
状态：已确认  
范围：全项目异常处理、loguru 按日落盘、故障码对照表、作业错误落库与终端堆栈。界面 tips 区分业务/系统，不展示故障码。  
产品语言：对象、属性、关系、定义、实例、父对象、编号、供应商、数据源。

## 1. 目标

任何失败都能在**后端终端和日志文件**里查到故障码、中文说明、`request_id` 和**完整堆栈**。业务校验与系统故障同一套记录，不只覆盖抽取。

**前端（tips、作业状态、HTTP 给界面用的 `detail`/`error`）只显示对用户的友好中文提示，不显示故障码，不显示堆栈。**

**一个码对应唯一固定中文句。** HTTP `detail`、作业 `error`、tips 文案必须与对照表完全一致，不得按调用点自由改写。

## 2. 日志

框架：loguru。进程启动（`create_app`）配置一次。

- 终端：stderr，INFO 及以上。
- 落盘：与数据目录同级的 `logs/ontocore_YYYY-MM-DD.log`（默认数据目录为 `./data` 时即 `./logs/`），**按自然日轮转**（每天 00:00 切文件），保留 14 天，UTF-8。
- ERROR 带完整 traceback（`exception=True`）。不开启 diagnose，避免把密钥写进日志。
- 每条含时间、级别、故障码（若有）、`request_id`（若有）。

测试用临时数据目录，不写本机 `backend/data/`。

## 3. 故障码对照表

稳定码 `OC-xxxx`。HTTP JSON：`detail`（中文，不含码）、`code`、`kind`（`business` | `system`）、`request_id`。

| 段 | 含义 | kind |
| --- | --- | --- |
| 1xxx | 入参校验、未找到 | business |
| 2xxx | 对象/属性/关系写入与约束 | business |
| 3xxx | 数据源作业：解析、抽取、嵌入、判重 | 供应商类失败为 business；未预期为 system |
| 4xxx | 图不可用等基础设施 | system |
| 5xxx | 设置页校验、拉取模型、测试 | business |
| 9xxx | 未捕获 | system |

### 3.1 完整对照（码 ↔ 固定提示）

| 码 | kind | HTTP | 固定提示 |
| --- | --- | --- | --- |
| OC-1101 | business | 400 | 请选择供应商 |
| OC-1102 | business | 400 | 请选择抽取模型 |
| OC-1103 | business | 400 | 请选择嵌入模型 |
| OC-1104 | business | 400 | 请选择嵌入供应商 |
| OC-1105 | business | 400 | 未找到所选供应商，请先在设置中添加 |
| OC-1106 | business | 400 | 未找到所选嵌入供应商，请先在设置中添加 |
| OC-1107 | business | 400 | 当前状态不能启动抽取 |
| OC-1108 | business | 400 | 上传文件已丢失，请重新新建作业 |
| OC-1109 | business | 400 | 当前状态不能修改作业 |
| OC-1004 | business | 404 | 未找到 |
| OC-2001 | business | 400 | 不符合对象关系约束 |
| OC-2002 | business | 400 | 无法写入对象、属性或关系 |
| OC-2003 | business | 409 | 与已有数据冲突 |
| OC-2004 | business | 409 | 仍有实例占用该对象 |
| OC-2005 | business | 409 | 仍有实例占用该属性 |
| OC-2006 | business | 409 | 仍有实例占用该关系 |
| OC-2007 | business | 400 | 请选择要对齐的已有对象或关系 |
| OC-3001 | business | 400 | 无法提取文本 |
| OC-3101 | business | 400 | 模型调用失败 |
| OC-3102 | business | 400 | 密钥无效或未填写，请检查 API Key |
| OC-3103 | business | 400 | 判重失败 |
| OC-3104 | business | 400 | 连接超时，请检查 Base URL 或网络 |
| OC-3105 | business | 400 | 无法连接服务，请检查网络 |
| OC-3106 | business | 400 | 接口不存在，请检查 Base URL 和模型名称 |
| OC-3107 | business | 400 | 请求过于频繁，请稍后再试 |
| OC-3108 | business | 400 | 服务已重启，请重新抽取 |
| OC-4001 | system | 503 | 图不可用 |
| OC-5001 | business | 400 | 请填写 Base URL |
| OC-5002 | business | 400 | 请填写 API Key |
| OC-5003 | business | 400 | 请选择具体模型 |
| OC-5004 | business | 400 | 密钥无效或未填写，请检查 API Key |
| OC-5005 | business | 400 | 连接超时，请检查 Base URL 或网络 |
| OC-5006 | business | 400 | 无法连接服务，请检查网络 |
| OC-5007 | business | 400 | 接口不存在，请检查 Base URL 和模型名称 |
| OC-5008 | business | 400 | 请求过于频繁，请稍后再试 |
| OC-5009 | business | 400 | 模型调用失败 |
| OC-9001 | system | 500 | 服务出错，请查看日志 |

说明：

- 设置校验用 OC-5001–5003；设置页供应商探测结果用 OC-5004–5009。
- 作业路径同类供应商问题用 OC-3102–3107；无法归类的模型失败用 OC-3101；进程重启中断作业用 OC-3108。
- 废弃「万能 OC-5001 覆盖所有设置失败」。
- 前端本地校验（如保存供应商「请填写名称、Base URL、API Key」）可直出 tips，**不占用 OC 码**（未打到后端）。

作业 `error` 只存对照表固定句，**不含** `OC-`，**不含** `Traceback`、文件路径或 Python 堆栈。另存 `error_kind`：`business` | `system`。完整堆栈只在终端和日志。

请求头可带 `X-Request-ID`；无则服务端生成。响应带回 `request_id`。

## 4. 落到代码

- **对照表实现**：`backend/src/ontocore/error_catalog.py` 常量字典 `OC-xxxx → {kind, http_status, detail}`，与 §3.1 一一对应；改文案只改该处与本规格。
- **抛错**：`AppError` 谱系以传 `code` 为主；`detail` / `kind` / `http_status` 从表取。不得手写与表冲突的中文。
- **供应商异常映射**：`map_provider_fault(raw, *, domain="settings"|"job") → code`。settings → OC-5004…5009；job → OC-3102…3107；无法归类 → OC-5009 或 OC-3101。再取表内文案，禁止把 `str(exc)` 原样返回界面。
- **HTTP 信封**不变：`{detail, code, kind, request_id}`，`detail` 必须是表内固定句。
- **前端**：tips / 作业状态只显示 `detail`，不渲染 `code`。`sanitizePublicError` 仅作断网与堆栈/HTML 兜底（文案与表中「无法连接服务…」「模型调用失败」一致）；供应商细分文案以后端为准。
- **测试**：对照表完整；抛码 → `detail` 等于表文；设置探测与作业路径映射到对应 5xxx / 31xx；前端不展示 `OC-`。

## 5. 行为（摘要）

- 领域异常与校验走统一处理：记日志、返回上述 JSON。
- 判重失败：作业 `partial`，`error` 为「判重失败」（OC-3103），`error_kind` 为 business。
- 未捕获：HTTP 500、OC-9001、`kind=system`、`detail` 为「服务出错，请查看日志」。
- tips 同一条文案只弹一条；HTTP 缺 `kind` 时界面按业务处理。
- 业务 tips 左边线 `#98a2b3`；系统 `#161b26`。

## 6. 新增功能时

凡新增或改动会失败的路径：必须选用或扩展 §3.1，经 `AppError` 谱系抛出；不得只抛裸异常或只返回无码字符串。新码按段递增并同步登记到对照表实现与本规格。开发约定见 [`docs/dev-standards.md`](../../dev-standards.md)「错误码与异常提示」。

## 7. 不做

- 界面展示故障码、堆栈、LiteLLM 异常类名或错误页 HTML（含把 `str(exc)` 原样丢给 tips）
- 调用点自由改写与对照表不一致的 `detail`
- 外部监控 / Sentry
- 把密钥或完整请求体打进日志
- 为本轮未覆盖的每个英文仓库异常再拆细码（其余归一到 OC-2001 / OC-2002）
