# OntoCore 设计：故障码与日志排查

日期：2026-09-21  
状态：已确认  
范围：全项目异常处理、loguru 按日落盘、故障码、作业错误落库与终端堆栈。界面 tips 区分业务/系统，不展示故障码。  
产品语言：对象、属性、关系、定义、实例、父对象、编号、供应商、数据源。

## 1. 目标

任何失败都能在**后端终端和日志文件**里查到故障码、中文说明、`request_id` 和**完整堆栈**。业务校验与系统故障同一套记录，不只覆盖抽取。**前端（tips、作业状态、HTTP 给界面用的 `detail`/`error`）只显示对用户的友好中文提示，不显示故障码，不显示堆栈。**

## 2. 日志

框架：loguru。进程启动（`create_app`）配置一次。

- 终端：stderr，INFO 及以上。
- 落盘：`{数据目录}/logs/ontocore_YYYY-MM-DD.log`，**按自然日轮转**（每天 00:00 切文件），保留 14 天，UTF-8。
- ERROR 带完整 traceback（`exception=True`）。不开启 diagnose，避免把密钥写进日志。
- 每条含时间、级别、故障码（若有）、`request_id`（若有）。

测试用临时数据目录，不写本机 `backend/data/`。

## 3. 故障码

稳定码 `OC-xxxx`。HTTP JSON：`detail`（中文，不含码）、`code`、`kind`（`business` | `system`）、`request_id`。

| 段 | 含义 | kind |
| --- | --- | --- |
| 1xxx | 入参校验、未找到 | business |
| 2xxx | 对象/属性/关系写入与约束 | business |
| 3xxx | 数据源作业：解析、抽取、嵌入、判重 | 抽取/嵌入供应商失败为 business；未预期异常为 system |
| 4xxx | 图不可用等基础设施 | system |
| 5xxx | 设置页拉取模型、测试 | business |
| 9xxx | 未捕获 | system |

常用码：

- `OC-1101` 请选择供应商
- `OC-1102` 请选择抽取模型
- `OC-1103` 请选择嵌入模型
- `OC-1104` 请选择嵌入供应商
- `OC-1105` 未找到所选供应商
- `OC-1106` 未找到所选嵌入供应商
- `OC-1004` 未找到（资源）
- `OC-2001` 约束/档案违规
- `OC-2002` 无法写入对象/属性/关系
- `OC-2003` 冲突
- `OC-3001` 无法提取文本
- `OC-3101` 抽取或模型调用失败
- `OC-3103` 判重失败
- `OC-4001` 图不可用
- `OC-5001` 设置拉取模型或测试失败
- `OC-9001` 未捕获系统异常

作业 `error` 只存友好中文（映射后的供应商说明，如密钥无效、连接超时），**不含** `OC-`，**不含** `Traceback`、文件路径或 Python 堆栈。另存 `error_kind`：`business` | `system`。完整堆栈只在终端和日志。

请求头可带 `X-Request-ID`；无则服务端生成。响应带回 `request_id`。

## 4. 行为

- 领域异常与校验走统一处理：记日志（业务异常也记，ERROR 带栈或至少带码与说明）、返回上述 JSON。
- 抽取块失败不再只写「抽取失败」四个字：日志打 LiteLLM/模型原始异常栈；作业 `error` 为可读中文（`public_llm_message`）。若原始异常像堆栈（含 `Traceback` 或 `File "`）、LiteLLM/异常类名，或 HTML（`rel=icon`、`data:image`、标签），对用户改为「模型调用失败」。断网、DNS 失败（如 `getaddrinfo`）改为「无法连接服务，请检查网络」，不要说成模型调用失败。不得把 `str(exc)` 截断后原样返回界面。设置页拉取模型、测试同样走该映射。
- 判重 `except` 记栈，作业 `partial` 且 `error` 为「判重失败」，`error_kind` 为 business。
- 未捕获：HTTP 500、`OC-9001`、`kind=system`、界面 `detail` 为「服务出错，请查看日志」；完整栈只在日志。

## 5. 界面

tips、作业状态文案只有友好中文。成功仍为主色左边线。打开供应商弹窗后拉取该供应商模型 / 测试失败也走同一套映射，不把供应商异常页 HTML 或 LiteLLM 类名送进 tips。同一条文案只弹一条 tips，不叠一摞。`ApiError` 与 `tipText` 再过滤一次，防止非 JSON 错误页漏到界面。HTTP 响应缺 `kind` 时界面按业务处理。

- 业务异常：左边线灰色 `#98a2b3`
- 系统异常：左边线近黑 `#161b26`

前端根据响应 `kind`（及作业 `error_kind`）选样式。不渲染 `code`。不渲染堆栈（含 `Traceback`、`.py` 行号、异常类名堆）。后端不得把 `traceback` 字段放进 JSON。

## 6. 不做

- 界面展示故障码、堆栈、LiteLLM 异常类名或错误页 HTML（含把 `str(exc)` 原样丢给 tips）
- 外部监控 / Sentry
- 把密钥或完整请求体打进日志
